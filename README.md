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

---

## What is implemented

### Latency models

- IID models (Gaussian, Exponential)
- Log-normal AR(1) (**CORRELATED**)
  - calibrated to match real latency distributions
  - preserves positivity without clamping
- Regime-switching latency (**REGIME / REGIME_CORRELATED**)
  - models congestion as a persistent state
  - produces realistic burst structure
- Queue-based congestion (**QUEUE**)
  - shared sender-side queue with bandwidth AR(1) noise
  - latency arises from message competition for a finite channel
  - creates a feedback loop: more agents → longer queues → higher latency
  - validated against batch-arrival analytical formula (0.00% error)

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
- `QueueLatencyModel` — mechanistic queue-based implementation
- `NetworkSimulator` — delayed message delivery
- `Agent` — distributed consensus algorithm
- `ExperimentLogger` — CSV output for system, network, and latency traces

---

## Key result: queue feedback loop

With identical channel parameters (bandwidth=70, noise σ=0.3, ρ=0.8) and algorithm (alpha=0.1, all-to-all consensus):

| Agents | Queue load (ρ) | Mean latency | Convergence step |
|--------|---------------|-------------|-----------------|
| 10     | 0.13          | 0.13 sec    | 160             |
| 50     | 0.70          | 0.60 sec    | 182             |
| 70     | 0.99          | 112 sec     | 836             |

Adding 20 agents (50 → 70) slowed convergence **5x** — not because the algorithm degraded, but because the network saturated. This effect is invisible in latency models where delay is independent of load.

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

This runs a multi-agent consensus experiment under the latency model specified in `config/config.json`. Results land in `results/run_<timestamp>/`, containing at least `latency.csv` (per-message delays) and `system.csv` (consensus state over time).

**2. Analyse the latency trace.** Point `analyze_latency.py` at the freshly-written CSV:

```bash
python3 analyze_latency.py results/run_<timestamp>/latency.csv out_run/
```

This produces `out_run/fit.json` with population statistics, per-link statistics, an AR(1) fit (both linear and log-normal variants), ACF, and burst statistics. Diagnostic plots are written to the same directory.

**3. Generate a quality report.** Compare the fitted parameters back against the trace they came from to check the model is consistent:

```bash
python3 temporis_report.py out_run/fit.json --mode correlated --output out_run/report.md
```

For a regime-switching run, use `--mode regime` and pass the same `config.json` you ran the simulation with:

```bash
python3 temporis_report.py out_run/fit.json --mode regime \
    --regime-config config/config.json --output out_run/report_regime.md
```

For a queue-based run, use `--mode queue`:

```bash
python3 temporis_report.py out_run/fit.json --mode queue \
    --regime-config config/config_queue.json --output out_run/report_queue.md
```

The report includes round-trip parameter recovery (CORRELATED only), marginal/burst/ACF comparison (REGIME), batch-arrival analytical check (QUEUE), and an explicit verdict section.

---

## Calibrating against real data (Path B: fit, configure, validate)

This is the workflow used for the validation paper: take a real public dataset, fit a stochastic model to it, plug the fitted parameters into `config.json`, run Temporis with those parameters, and verify that the simulator reproduces the source statistics.

**1. Get the data.** The Seattle dataset is publicly available at https://github.com/uofa-rzhu3/NetLatency-Data. Clone or download it, then convert it to Temporis CSV format with the bundled parser:

```bash
python3 parse_seattle.py /path/to/SeattleData/ results/seattle/data_real.csv
```

The parser reads matrix-per-file Seattle format and emits a canonical `t, sender, receiver, delay` CSV. If you want to use a different dataset, write a similar parser — the only contract is that the output CSV has those four columns.

**2. Fit a log-normal AR(1) to the real trace.**

```bash
python3 analyze_latency.py results/seattle/data_real.csv out_seattle/
```

The output `out_seattle/fit.json` contains the per-link AR(1) fit under `per_link.ar1_fit_log` — specifically `base_delay`, `rho`, and `innovation_std`. Copy these three numbers into the `latency` block of `config/config.json` to use them in a CORRELATED simulation.

**3. (Optional) Search for regime-switching parameters.** A single-regime AR(1) cannot reproduce long burst episodes seen in real traces. To fit a Markov-switching variant, run a Bayesian optimization search:

```bash
python3 fit_regime_bayesian.py out_seattle/fit.json \
    --target-csv results/seattle/data_real.csv \
    --trials 500 --loss v2 \
    --save-config out_seattle/best_regime.json
```

Or a simpler grid search:

```bash
python3 fit_regime_correlated.py out_seattle/fit.json
```

**4. Run Temporis with the calibrated parameters.**

```bash
./build/consensus_demo config/config.json
```

**5. Validate the simulator against the real source.**

```bash
python3 temporis_report.py out_seattle/fit.json --mode regime \
    --regime-config config/config.json --output out_seattle/report.md
```

The verdict section will tell you whether the calibration succeeded — and crucially, it will warn you if the regime model overshoots long-range autocorrelation, which is a known limitation of Markov-switching log-AR(1) and the topic of ongoing work.

---

## Pipeline tools

| Tool | Input | Output | Purpose |
|---|---|---|---|
| `parse_seattle.py` | raw Seattle dataset directory | canonical CSV | Convert public Seattle RTT data to Temporis format |
| `analyze_latency.py` | latency CSV (real or simulated) | `fit.json` + plots | Population/per-link statistics, AR(1) fit, ACF, bursts |
| `fit_regime_correlated.py` | target `fit.json` | regime config (printed) | Grid search for Markov-switching parameters |
| `fit_regime_bayesian.py` | target `fit.json` + CSV | regime config (saved) | Bayesian optimization with configurable loss (v1/v2/v3) |
| `temporis_report.py` | `fit.json` + mode + config | `report.md` + plots | Quality report with analytical checks and verdicts |

All scripts have `--help`. None depend on running C++ — they operate on CSVs and JSON.

---

## Research directions

Temporis is designed for studying:

- latency-induced instability in multi-agent systems
- interaction between communication and control
- robustness of consensus under realistic delays
- scaling effects: how adding agents changes network dynamics

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

### Planned

- ROS2 integration
- Zenoh backend support:
  - Adapt queue model to Zenoh-specific topology (peer / client+router / mesh)
  - Validate against real Zenoh latency measurements
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