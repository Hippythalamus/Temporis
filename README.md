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
- Zenoh client+router topology (**ZENOH_QUEUE**) — two-stage queue (client egress → router forwarding → subscriber), router processes all messages from all clients (O(N²) work)

### Validation and calibration

- Round-trip parameter recovery pipeline
- Distribution matching (mean, std, p95, p99)
- Temporal metrics (ACF, burst statistics)
- Bayesian optimization for regime calibration (optuna)
- Automated quality reports with explicit verdicts

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

## Key result: topology determines stability

Same algorithm (alpha=0.1, all-to-all consensus), same channel parameters (bandwidth=70, noise σ=0.3, ρ=0.8), two different middleware topologies:

| Agents | QUEUE mean | ZENOH mean | QUEUE conv. step | ZENOH conv. step |
|--------|-----------|-----------|-----------------|-----------------|
| 10     | 0.13 sec  | 0.22 sec  | 161             | 162             |
| 50     | 0.60 sec  | 3.84 sec  | 182             | 402             |
| 70     | 112 sec   | 206 sec   | 836             | **does not converge** |

At N=70, peer-to-peer topology (QUEUE) converges in 836 steps. Client+router topology (ZENOH_QUEUE) **does not converge** within 6387 steps — final variance is 0.087, twenty-six orders of magnitude worse.

The only difference is the router. It creates an O(N²) bottleneck: every published message must be forwarded to N-1 subscribers sequentially. At N=70, the router processes 4830 messages per step at ~203 μs each — nearly 1 second of work per 1-second step, pushing the system into saturation.

The ZENOH_QUEUE model captures the qualitative topology of Zenoh client+router deployments (single shared router, sequential per-subscriber forwarding) but uses approximate processing costs. The specific saturation thresholds shown above will differ from real Zenoh deployments, where batching, parallelism, and protocol-level optimizations may raise or lower the critical N. Validation against real Zenoh router traces is planned.

This effect is invisible in any latency model where delay is independent of load or topology.

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
- Queue feedback loop experiment (N=10/50/70 convergence comparison)
- Zenoh client+router queue model (two-stage, O(N²) router bottleneck)
- Topology comparison experiment (QUEUE vs ZENOH_QUEUE stability)

### Planned

- ROS2 integration
- Zenoh validation against real router traces
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