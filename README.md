# Temporis
**Structured latency as a first-class experimental variable**

Temporis is a framework for simulating **time-dependent, stochastic network latency** and studying how it affects multi-agent system behavior.

Unlike traditional tools, Temporis treats latency not as noise — but as a **dynamic process with structure, memory, and regimes**.

---

## Why this matters

Most simulations assume latency is:
- constant
- or IID noise

But real systems don't behave like that.

Real network latency has:
- temporal correlation
- heavy-tailed distributions
- bursty congestion episodes

This mismatch creates a **sim-to-real gap**:
algorithms that converge in simulation can become unstable in reality.

Temporis is built to close that gap.

---

## Core idea

> System behavior depends not on *how much* latency you have,
> but on *how latency evolves over time*.

Temporis lets you test:

- same mean latency → different system dynamics
- short noise vs long bursts
- effect of temporal correlation on convergence
- effect of middleware topology on scaling

---

## What is implemented

### Latency models

- IID models (Gaussian, Exponential)
- Log-normal AR(1) (**CORRELATED**) — calibrated to match real latency distributions, preserves positivity without clamping
- Regime-switching latency (**REGIME / REGIME_CORRELATED**) — models congestion as a persistent state, produces realistic burst structure
- Queue-based congestion (**QUEUE**) — shared sender-side queue with bandwidth AR(1) noise, validated against batch-arrival formula (0.00% error)
- Zenoh client+router topology (**ZENOH_QUEUE**) — two-stage queue (client egress → router forwarding → subscriber), calibrated against real Zenoh all-to-all benchmark (router_base_cost=108μs, router_per_sub_cost=2.7μs)

### Validation and calibration

- Round-trip parameter recovery pipeline
- Distribution matching (mean, std, p95, p99)
- Temporal metrics (ACF, burst statistics)
- Bayesian optimization for regime calibration (optuna)
- Automated quality reports with explicit verdicts
- Real Zenoh benchmark (fan-out + all-to-all) for router parameter extraction

---

## Architecture

- `LatencyModel` — abstract base for all latency processes
- `RegimeLatencyModel` — IID, AR(1), and regime-switching implementations
- `QueueLatencyModel` — mechanistic shared-sender queue
- `ZenohQueueModel` — two-stage client+router queue
- `NetworkSimulator` — delayed message delivery
- `Agent` — distributed consensus algorithm
- `ExperimentLogger` — CSV output for system, network, and latency traces

---

## Key results

### Regime-switching: Pareto frontier (Etap 2)

Two-regime Markov-switching log-AR(1) cannot simultaneously match
marginal distribution, burst structure, and short-range ACF of Seattle
traces. Three calibration strategies (grid search baseline, Bayesian
optimization weighted toward ACF, and weighted toward burst length)
map three points on a trade-off surface:

| Metric      | Seattle | Baseline | Optuna v2 (ACF) | Optuna v3 (burst) |
|-------------|---------|----------|-----------------|-------------------|
| std error   |    —    | +19%     | -33%            | -4%               |
| ACF lag 1   | 0.815   | ~0.96    | 0.799           | 0.940             |
| burst mean  | 5.83    | +33%     | -42%            | -31%              |

**Conclusion.** This is a structural limitation of the two-regime
Markov-switching model class, not a calibration failure. Optimizing
for ACF breaks burst statistics and vice versa — no weighting escapes
the trade-off. This motivates mechanistic (queue-based) models that
generate temporal structure from physical dynamics rather than fitting
it from abstract parameters.

### Queue feedback loop (Etap 3)

With queue-based latency (shared sender, bandwidth AR(1) noise),
adding agents increases message load, which increases queueing delay,
which degrades consensus convergence. This feedback loop is absent
in all phenomenological models (IID, CORRELATED, REGIME) where delay
is independent of the number of communicating agents:

| Agents | Mean latency | Convergence step |
|--------|-------------|-----------------|
| 10     | 0.13 sec    | 161             |
| 50     | 0.60 sec    | 182             |
| 70     | 112 sec     | 836             |

**Conclusion.** Adding 20 agents (50 → 70) slowed convergence 5x —
not because the consensus algorithm degraded, but because the sender's
outgoing queue saturated. This is the first experiment in Temporis where
system behavior depends on the number of agents through network dynamics,
not through algorithm structure. Any simulation that ignores load-dependent
latency will miss this effect entirely.

### Topology determines stability (Etap 4)

Same algorithm (alpha=0.1, all-to-all), same channel parameters
(bandwidth=70, noise σ=0.3, ρ=0.8), two different middleware topologies
— peer-to-peer (QUEUE) and client+router (ZENOH_QUEUE):

| Agents | QUEUE mean | ZENOH mean | QUEUE conv. | ZENOH conv. |
|--------|-----------|-----------|-------------|-------------|
| 10     | 0.13 sec  | 0.22 sec  | 161         | 162         |
| 50     | 0.60 sec  | 3.84 sec  | 182         | 402         |
| 70     | 112 sec   | 206 sec   | 836         | **does not converge** |

**Conclusion.** At N=70, peer-to-peer converges in 836 steps while
client+router does not converge at all (final variance 0.087). The only
difference is the router, which creates an O(N²) bottleneck: every
published message must be forwarded to N-1 subscribers. Same algorithm,
same bandwidth — different middleware topology produces a qualitatively
different outcome. This effect is invisible in any latency model where
delay is independent of topology.

### Calibrated Zenoh saturation threshold (Etap 4)

ZenohQueueModel calibrated from a real Zenoh all-to-all benchmark
(router_base_cost=108μs, router_per_sub_cost=2.7μs, linear fit error <1%):

| Agents | Mean latency | Router ρ | Convergence |
|--------|-------------|----------|-------------|
| 10     | 16 ms       | 0.01     | 160 steps   |
| 50     | 339 ms      | 0.59     | 174 steps   |
| 60     | 525 ms      | 0.95     | 175 steps   |
| 70     | 1347 sec    | 1.42     | **does not converge** |

**Conclusion.** Single-router Zenoh topology supports all-to-all
consensus up to approximately 65 agents. Beyond this threshold, the
router's processing time exceeds the simulation step (ρ > 1), latency
grows without bound, and consensus diverges. In practice, peer-to-peer
Zenoh breaks even earlier — at N≈50 — due to discovery storm (each
peer must find N-1 others via gossip). Neither standard Zenoh topology
scales indefinitely for all-to-all communication; large deployments
require either sparse communication patterns (ring, grid, random
neighbors) or multi-router mesh architectures.
---

## Dependencies

Python tools require:

- numpy
- pandas
- matplotlib
- optuna

## Build

```bash
mkdir build
cd build
cmake ..
make
```

---

## Tests

```bash
# With pytest
python3 -m pytest tests/test_fit.py -v

# Without pytest
python3 tests/test_fit.py
```

## Quick start (Path A: simulate and analyse)

The fastest way to see Temporis in action is to run the bundled `consensus_demo` with the default config, then analyse what it produced. No external data required.

**1. Run a simulation.** From the repo root, after building:

```bash
./build/consensus_demo config/config.json
```

Results land in `results/run_<timestamp>/`, containing `latency.csv` (per-message delays) and `system.csv` (consensus state over time).

**2. Analyse the latency trace.**

```bash
python3 analyze_latency.py results/run_<timestamp>/latency.csv out_run/
```

Produces `out_run/fit.json` with population and per-link statistics, AR(1) fit, ACF, and burst statistics.

**3. Generate a quality report.**

```bash
python3 temporis_report.py out_run/fit.json --mode correlated --output out_run/report.md
```

For regime-switching: `--mode regime --regime-config config/config.json`

For queue-based: `--mode queue --regime-config config/config_queue.json`

---

## Calibrating against real data (Path B: fit, configure, validate)

**1. Get the data.** The Seattle dataset is publicly available at https://github.com/uofa-rzhu3/NetLatency-Data.

```bash
python3 parse_seattle.py /path/to/SeattleData/ results/seattle/data_real.csv
```

**2. Fit a log-normal AR(1).**

```bash
python3 analyze_latency.py results/seattle/data_real.csv out_seattle/
```

**3. (Optional) Search for regime-switching parameters.**

```bash
python3 fit_regime_bayesian.py out_seattle/fit.json \
    --target-csv results/seattle/data_real.csv \
    --trials 500 --loss v2 \
    --save-config out_seattle/best_regime.json
```

**4. Run and validate.**

```bash
./build/consensus_demo config/config.json
python3 temporis_report.py out_seattle/fit.json --mode regime \
    --regime-config config/config.json --output out_seattle/report.md
```

---

## Pipeline tools

| Tool | Input | Output | Purpose |
|---|---|---|---|
| `parse_seattle.py` | raw Seattle dataset directory | canonical CSV | Convert public Seattle RTT data to Temporis format |
| `analyze_latency.py` | latency CSV (real or simulated) | `fit.json` + plots | Population/per-link statistics, AR(1) fit, ACF, bursts |
| `fit_regime_correlated.py` | target `fit.json` | regime config (printed) | Grid search for Markov-switching parameters |
| `fit_regime_bayesian.py` | target `fit.json` + CSV | regime config (saved) | Bayesian optimization with configurable loss (v1/v2/v3) |
| `temporis_report.py` | `fit.json` + mode + config | `report.md` + plots | Quality report with analytical checks and verdicts |

---

## Roadmap

### Done

- Log-normal AR(1) latency model (CORRELATED)
- Correct calibration (mean-preserving log transform)
- Round-trip validation pipeline
- Regime-switching latency (burst modeling)
- Basic multi-agent consensus simulation
- Quality report tool with explicit verdicts
- Bayesian regime calibration with Pareto frontier analysis
- Queue-based congestion model with bandwidth AR(1) noise
- Queue feedback loop experiment (N scaling comparison)
- Zenoh client+router queue model (two-stage, O(N²) router bottleneck)
- Zenoh calibration from real all-to-all benchmark (108μs base, 2.7μs/sub)
- Saturation threshold: N≈65 for single-router all-to-all consensus

### Planned

- Sparse communication topologies (ring, grid, random neighbors)
- Multi-router mesh topology
- ROS2 integration (Temporis as ROS2 node)
- Phase transition detection tools
- Hybrid models (queue + regime-switching)

---

## Contributing

Contributions are welcome, especially in:

- new latency models
- real-world calibration datasets
- multi-agent scenarios
- robotics integration

---

## Final note

Temporis is built on a simple observation:

> If your latency model is wrong, your conclusions about the system will be wrong.

This project is an attempt to make latency modeling **less naive and more honest**.