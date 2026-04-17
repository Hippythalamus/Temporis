# Queue-based latency model — specification

This document defines the queue-based latency model planned for Temporis (roadmap item: *Queue-based congestion model*). It is a design specification, not an implementation guide. It fixes the design decisions made before any C++ code is written, so the implementation can proceed without re-deriving choices on the fly.

---

## 1. Motivation

The two latency models currently in Temporis — `CORRELATED` (log-normal AR(1)) and `REGIME_CORRELATED` (Markov-switching log-normal AR(1)) — are **phenomenological**: they reproduce observed latency statistics by fitting parameters of an abstract stochastic process. Calibration against the Seattle dataset (Etap 2) showed that the two-regime model has a structural limitation: it cannot simultaneously match marginal distribution, burst structure, and short-range autocorrelation, and no choice of weights in the loss function escapes this trade-off.

The queue-based model is **mechanistic**: latency arises as an observable consequence of message arrivals competing for a finite-capacity channel. The model's parameters describe the physical channel (bandwidth, propagation delay, channel noise) rather than the resulting statistics. This shifts calibration from "match the statistics directly" to "find channel parameters that produce the observed statistics", which is a richer and physically more defensible problem.

A second motivation is closing the feedback loop. In the existing models, agent behavior does not affect latency. In the queue-based model, the rate at which agents send messages determines queue depth, which determines latency. This makes Temporis suitable for the original research question — *does the temporal structure of latency affect multi-agent algorithm behavior* — because for the first time, the algorithm and the network are coupled.

---

## 2. Queue placement

Each directed link `(i, j)` in the simulated network has an associated queue. Two physically meaningful placements are supported, controlled by the configuration field `queue_side`:

**`queue_side: "sender" (default)`.**Each sender i maintains one shared outgoing queue for all destinations. Messages from i to any receiver accumulate in this single queue and are served at the sender’s available bandwidth. Messages destined for different receivers therefore compete for the same sender-side resource, and congestion created by traffic to one receiver affects latency to all others. Queues at different senders are independent: congestion at one sender does not affect others. This placement models systems where the bottleneck is the sender's last-mile link to the network — typical for wireless devices, mobile clients, and home internet connections. It is the right default for distributed systems with all-to-all or peer-to-peer topology, where no node plays a central role.

**`queue_side: "receiver"`.** Each receiver `j` maintains one incoming queue, into which messages from all senders are merged in arrival order and served at the receiver's bandwidth. Messages from different senders compete for the same receiver-side resource. This placement models systems where the bottleneck is at the receiver — typical for star topologies, leader-follower architectures, and any setup where many nodes report to one. It is the right choice when modeling a coordinator or aggregator under load.

Both placements are first-class. The simulator dispatches on `queue_side` once at experiment start and uses the corresponding queue layout throughout.

A third placement — a single shared queue for the whole network — is not supported. It would model a shared broadcast channel (legacy Ethernet hub, single shared radio frequency), which is rare in modern distributed systems and not relevant for our target use cases. It can be added later as a third option if a specific experiment requires it.

---

## 3. Service rate

The queue is served at a rate determined by the channel's bandwidth and the size of each message. The time required to serve one message of size `s` bytes at instantaneous bandwidth `b` bytes per second is `s / b` seconds. This is the classical serialization delay.

The configuration exposes:

- **`bandwidth_mean`**: mean channel bandwidth in bytes per second
- **`packet_size`**: message size in bytes; if all messages in the experiment are uniform, this is taken from the configuration; otherwise the per-message size is used (the message header carries it)

Parameterising through bandwidth and packet size — rather than an abstract "messages per second" rate — has two benefits. First, it is physically faithful: real channels are bandwidth-limited, not message-rate-limited. Second, it generalises naturally to heterogeneous message sizes: if the consensus protocol later sends both small heartbeats and large state updates, no model change is needed.

The pre-existing fields `bandwidth: 1000.0` and `packet_size: 1` in `config.json`, which were unused by the previous models, become semantically meaningful under this model.

---

## 4. Per-message delay computation

Each message `m` in the simulation has an arrival time at the queue, `t_arrival(m)`, and a completion time at which it leaves the queue and starts propagating to the destination, `t_complete(m)`. The observed latency of `m` is

```
latency(m) = (t_complete(m) - t_arrival(m)) + propagation_delay
```

where the first term is **queueing + serialization delay** and the second is the fixed **propagation delay** of the link.

The completion time is computed using the standard recursion for a single-server queue:

```
t_complete(m) = max(t_arrival(m), t_complete(prev_m)) + service_time(m)
```

where `prev_m` is the previous message served by the same queue. The `max` reflects the fact that if the queue is empty when `m` arrives, it begins service immediately; if the queue is busy, it waits until the previous message finishes.

The service time is

```
service_time(m) = packet_size(m) / bandwidth(t)
```

evaluated at the time the message begins service. If bandwidth is constant (`bandwidth_logstd = 0`), this is simply `packet_size / bandwidth_mean`. If bandwidth is time-varying (Section 5), the value at the instant of service entry is used.

This is the **exact event-driven** computation, not a per-step approximation. It is justified because in our setting the simulation step `dt = 1.0` is much larger than typical service times (`packet_size / bandwidth_mean ~ 0.001 s` for the default values), so multiple messages may pass through a single queue within one step. A per-step approximation would aggregate them incorrectly. The event-driven formula above handles all such cases without distortion. Implementation-wise, the queue stores `(t_arrival, packet_size)` for each pending message and updates a running `t_complete` cursor.

**Tie-breaking on simultaneous arrivals.** When several messages arrive at the same queue within the same simulation step (which happens routinely in `consensus_demo`, where all agents send at every step), they nominally share the same `t_arrival = step * dt`. Resolving their order would otherwise depend on the iteration order of the C++ data structures, which is not a physically meaningful quantity and risks silently coupling results to implementation details. To avoid this, a tiny deterministic offset is added based on sender identity:

```
t_real = t_arrival + sender_id * EPS,    EPS = 1e-9 seconds
```

The offset is **purely a tie-breaking artifact for queue accounting, not physical time**. It is six or more orders of magnitude smaller than any physically meaningful latency scale (typical service times are at least 1e-5 s, propagation delays at least 1e-3 s), so it does not appear in any downstream statistic — marginal distribution, percentiles, ACF, or burst structure are all unaffected. It exists solely to make the order in which simultaneously-arriving messages enter the queue reproducible across runs and independent of language, compiler, or container.

An earlier formulation scaled the offset by `dt / num_agents` so that arrivals would be evenly spread across the simulation step. That formulation was rejected because it introduces a fictitious deterministic temporal structure (sender 49 always offset by 20 ms relative to sender 0 at `dt = 1`, `N = 50`) which can produce spurious autocorrelation and even resonate with the physical service time scale. The epsilon-based tie-break has none of these effects.

---

## 5. Sources of randomness

Real network latency varies even under nominally constant load. The model includes two physically distinct, independently configurable sources of variation. Both default to zero, in which case the model reduces to a deterministic M/D/1 queue useful as a sanity-check baseline.

**Source A — bandwidth fluctuation.** The instantaneous bandwidth of the channel varies over time:

```
bandwidth(t) = bandwidth_mean * exp(epsilon(t))
```

where `epsilon(t)` is a stochastic process with mean zero. To match the temporal structure of real channels — which exhibit slow fluctuations, not white noise — `epsilon` is modeled as an AR(1) process with two parameters:

- **`bandwidth_logstd`**: standard deviation of `epsilon` in log-space
- **`bandwidth_rho`**: lag-1 autocorrelation of `epsilon`

If `bandwidth_rho = 0`, the bandwidth is white-noise log-normal. If `bandwidth_rho` is close to 1, the bandwidth exhibits slow drifts on the order of `1 / (1 - rho)` simulation steps. This source models WiFi quality variation, cellular network conditions, and contention from background traffic that we do not simulate explicitly. It is the dominant source for wireless deployments.

**Source B — service-time noise.** Each message receives an additional multiplicative noise on its service time, independent across messages:

```
service_time(m) = (packet_size(m) / bandwidth(t)) * exp(delta(m))
```

where `delta(m)` is i.i.d. normal with mean zero and standard deviation `service_noise_logstd`. This source models packet-by-packet variation in router or receiver processing time — cache misses, brief CPU spikes, garbage collection pauses. It is the dominant source for software-defined networks and for systems with heavyweight per-message processing (decryption, deserialization).

The two sources are independent and can be enabled separately. Setting both to zero gives a fully deterministic queue, useful for verifying that the implementation matches analytical M/D/1 results.

A third potential source — variable arrival times — is not modeled here, because in our simulation the arrival schedule is fully determined by agent behavior and is therefore observable rather than stochastic. We do not need to inject artificial arrival jitter.

**Sampling discipline.** Bandwidth is sampled **once per message at the moment that message enters service**, not integrated over the duration of service. For long service times during which bandwidth would change, this is an approximation. It is acceptable because typical service times in our setting are much shorter than the bandwidth correlation time: at default parameters, service time is on the order of `0.001 s` while bandwidth changes on the order of one simulation step (`1.0 s`). The approximation is recorded explicitly here so that future readers do not assume a continuous-time integration.

**Note on time scale.** Bandwidth dynamics evolve on the simulation step `dt`, not on individual queue events. Within a single step, bandwidth is constant for all messages served during that step. This is a deliberate approximation: autocorrelation of latency on lags shorter than one simulation step is smoothed compared to a true continuous-time model where bandwidth varies continuously. For the default `dt = 1.0` and typical service times around `0.001 s` this affects only sub-step scales, which are not observable in our pipeline since `analyze_latency.py` operates on per-message latencies aggregated at the `dt` resolution. If higher temporal fidelity is required in future work, the bandwidth process can be re-sampled at a finer rate independent of `dt`.

---

## 6. Queue capacity and overflow

By default the queue is unbounded (`queue_capacity: -1`). This is appropriate for studying steady-state behavior under stable load, where queues do not grow without bound.

If `queue_capacity` is set to a positive integer N, the queue holds at most N pending messages. Messages arriving when the queue is full are **dropped**: they are logged as drops in the output CSV but are never delivered to the destination. This matches the behavior of real network buffers under overload (tail drop in router queues).

Drops are observable by downstream code: the `latency.csv` format gains an additional column or marker indicating dropped messages. Agents that need to detect message loss can do so at the application level.

The default of unbounded queues is a deliberate choice for the first version: it avoids the additional complexity of agents needing to handle losses, and it allows the model to exhibit unbounded queue growth under sustained overload, which is itself a meaningful diagnostic ("the chosen parameters are infeasible for this load"). Bounded queues with drop are available when overload behavior is the object of study.

---

## 7. Configuration parameters summary

The complete `latency` block in `config.json` for the queue-based model:

```json
"latency": {
  "model": "QUEUE",
  "queue_side": "sender",
  "bandwidth_mean": 1000.0,
  "propagation_delay": 0.05,
  "packet_size": 1,
  "bandwidth_logstd": 0.0,
  "bandwidth_rho": 0.0,
  "service_noise_logstd": 0.0,
  "queue_capacity": -1
}
```

Required fields: `model`, `queue_side`, `bandwidth_mean`, `propagation_delay`, `packet_size`. The four optional fields default to zero or unbounded as shown.

This is fewer parameters than `REGIME_CORRELATED` (seven), and each parameter has a clear physical meaning and unit, which makes calibration interpretable in terms of channel characteristics rather than abstract distributional moments.

---

## 8. Edge cases and degenerate configurations

**Empty queue.** A message arriving at an empty queue begins service immediately: `t_complete = t_arrival + service_time`. No special handling required.

**Zero bandwidth.** Configuration must reject `bandwidth_mean <= 0` at startup with a clear error message. Service time is undefined for zero bandwidth.

**Bandwidth realisation near zero.** With large `bandwidth_logstd`, sampled bandwidth can become arbitrarily small, producing arbitrarily large service times. This is physically meaningful (channel temporarily unavailable) but can stall the queue indefinitely. A floor `min_bandwidth = bandwidth_mean / 100` is applied to the sampled value to prevent simulation lockup. Because this floor truncates the lower tail of the bandwidth distribution and therefore distorts the upper tail of the latency distribution (p99, p999, max), the simulator must report at experiment end:

- the **count** of times the floor was triggered
- the **percentage** of messages whose service time was affected
- the **maximum** ratio `bandwidth_mean / sampled_bandwidth` that occurred before the floor was applied

If the affected fraction exceeds 1% of messages, this should appear as an explicit warning, since downstream statistics (especially p99 and max) cannot be trusted to reflect the model's uncensored behavior.

**Saturation.** If the average arrival rate exceeds `bandwidth_mean / packet_size`, the queue grows without bound and observed latency diverges. This is the M/D/1 saturation condition `rho >= 1`. The simulator does not prevent this — it is a meaningful outcome that signals the configuration is infeasible. Diagnostic output should report the realised arrival rate and traffic intensity at experiment end.

**Initial state.** All queues start empty at `t = 0`. The first message at any link experiences only its own service time plus propagation delay.

---

## 9. Relationship to existing models

The queue-based model does not subsume `CORRELATED` or `REGIME_CORRELATED`; it is a different class of model. However, certain limiting cases are informative:

- With `bandwidth_logstd = 0`, `service_noise_logstd = 0`, and constant arrival rate, the model produces deterministic latency proportional to queue length. This is **not** a special case of CORRELATED.
- With high `bandwidth_logstd`, slowly-varying bandwidth (`bandwidth_rho` close to 1), and arrival rate well below saturation, queue effects become negligible and the model approximates a log-normal AR(1) process on the `1 / bandwidth(t)` term. In this regime it behaves similarly to `CORRELATED`.
- The Markov-switching structure of `REGIME_CORRELATED` has no direct analogue: queue-based congestion produces persistent high-latency episodes when arrival rate temporarily exceeds service rate, but the persistence is driven by queue depth dynamics rather than by an abstract hidden state.

Calibration against Seattle (planned for Etap 3 step 3) will determine which regimes of the queue model best reproduce real observed statistics, and whether the model can match metrics — particularly the long-range autocorrelation bump at lag ~10 — that the previous models could not.

---

## 10. Calibration methodology and identifiability

The two randomness parameters `bandwidth_logstd` and `service_noise_logstd` are not fully identifiable from latency observations alone. Both contribute multiplicatively to log-service-time variance, and naive simultaneous fitting of both will leave the optimizer wandering along a ridge of equally good loss values:

```
log_var_total = bandwidth_logstd^2 + service_noise_logstd^2
```

Their physical effects do differ — `bandwidth_logstd` combined with non-zero `bandwidth_rho` produces **temporally correlated** noise, while `service_noise_logstd` is i.i.d. across messages. This means they can in principle be distinguished through ACF, but only if `bandwidth_rho > 0`. When `bandwidth_rho = 0`, the two parameters are fully indistinguishable.

The recommended calibration discipline is therefore:

1. **First iteration:** fix `service_noise_logstd = 0` and let the optimizer fit `bandwidth_logstd` and `bandwidth_rho`. This treats all variability as coming from the channel, which is a defensible default and matches the focus of Etap 3 step 2 (introducing one source of randomness).
2. **Second iteration (if needed):** if the first iteration cannot match observed statistics — particularly if observed ACF decays faster than any `bandwidth_rho` setting can reproduce — fix `bandwidth_logstd` at the value found in step 1 and let the optimizer fit `service_noise_logstd`. This isolates the second mechanism.
3. **Joint fitting:** only attempt joint fitting of both noise parameters if there is a specific reason to believe both mechanisms are physically present and the ACF data is rich enough to disentangle them.

This avoids the failure mode where Bayesian optimization produces equivalent loss for many different parameter combinations, leaving the modeller unable to make defensible claims about which physical mechanism dominates.

---

## 11. Out of scope for this version

The following are deliberately deferred to keep the first implementation focused:

- **Heterogeneous link parameters.** All links share the same `bandwidth_mean`, `propagation_delay`, etc. Per-link parameters are a natural extension once the homogeneous version is validated.
- **Multi-hop routing.** Messages travel directly from sender to receiver through one queue. Realistic multi-hop networks would compose multiple queues per path. Not needed for current consensus experiments.
- **Protocol effects.** TCP-like backpressure, ACK-based windowing, retransmission on drop are not modeled. The transport layer is assumed to be UDP-like (fire-and-forget).
- **Topology-dependent bandwidth.** All links have the same nominal bandwidth. Modeling shared upstream links (where multiple sender queues compete for one physical channel) is out of scope.
- **Zenoh-specific topology.** The model is currently transport-agnostic and assumes a generic shared sender-side queue. Real Zenoh deployments have several distinct queue topologies (peer-to-peer per-link queues in peer mode; client + router two-stage queues in client mode; mesh of routers in production scale). Adapting this model to specific Zenoh deployment modes is planned as a separate effort in Etap 4. The current implementation is intended as a generic baseline for studying queue impact on multi-agent algorithms, not as a faithful predictor of Zenoh production latency.

These are good extensions for future work but each adds a meaningful chunk of complexity, and the goal of this iteration is the minimal physically-meaningful queue model.