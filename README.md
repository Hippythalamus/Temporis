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

These models are validated via:
- round-trip parameter recovery
- distribution matching (mean, std, p95, p99)
- temporal metrics (ACF, burst statistics)

---

## Architecture

- `LatencyModel` — stochastic latency process
- `NetworkSimulator` — delayed message delivery
- `Agents` — distributed algorithms
- `Experiment` — execution + metrics

---

## Example: why structure matters

Temporis is built around the idea that two latency processes can have the **same average** but very different temporal structure — different burst statistics, different long-range correlation, different ACF decay. Whether this translates into measurable differences in distributed-system behavior depends on the specific algorithm and topology. The validation methodology in this repo is designed to make those differences visible and reproducible; demonstrating their downstream impact on consensus, formation control, and similar algorithms is the subject of ongoing work.

---

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

The report includes round-trip parameter recovery (CORRELATED only), marginal/burst/ACF comparison against the source trace, and an explicit verdict section that flags issues like ACF mismatch, sampling-variance warnings, or near-unit-root `rho`.

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

**3. (Optional) Search for regime-switching parameters.** A single-regime AR(1) cannot reproduce long burst episodes seen in real traces. To fit a Markov-switching variant, run a grid search against the target statistics:

```bash
python3 fit_regime_correlated.py out_seattle/fit.json
```

This prints the best regime configuration as a JSON block. Copy it into the `latency` block of `config/config.json` and switch the experiment mode to `REGIME_CORRELATED`.

**4. Run Temporis with the calibrated parameters.**

```bash
./build/consensus_demo config/config.json
```

**5. Validate the simulator against the real source.** This is the key honesty step — run the report with the **real** `fit.json` as the target, but the **calibrated** config as the regime model. The report compares simulated traces (drawn fresh from the model) against the real Seattle trace:

```bash
python3 temporis_report.py out_seattle/fit.json --mode regime \
    --regime-config config/config.json --output out_seattle/report.md
```

The verdict section will tell you whether the calibration succeeded — and crucially, it will warn you if the regime model overshoots long-range autocorrelation, which is a known limitation of Markov-switching log-AR(1) and the topic of ongoing work.

---

## Pipeline tools

The Python side of Temporis is three small CLI tools that share a common library (`temporis/fit/`):

| Tool | Input | Output | Purpose |
|---|---|---|---|
| `parse_seattle.py` | raw Seattle dataset directory | canonical CSV (`t, sender, receiver, delay`) | Convert public Seattle RTT data to the format Temporis expects. Replaceable per-dataset. |
| `analyze_latency.py` | latency CSV (real or simulated) | `fit.json` + diagnostic plots | Compute population and per-link statistics, fit linear and log-normal AR(1), measure ACF and bursts. |
| `fit_regime_correlated.py` | target `fit.json` | best regime config (printed) | Random search over Markov-switching log-AR(1) parameters to match target marginal and burst statistics. |
| `temporis_report.py` | `fit.json` + mode (+ regime config) | `report.md` + 3 plots | Round-trip validation, marginal/burst/ACF comparison against target, explicit verdict with warnings. |

All four scripts have `--help`. None of them depend on running C++ — they operate on CSVs and JSON, so you can use them on any latency dataset that follows the canonical four-column format.

---

## Research directions

Temporis is designed for studying:

- latency-induced instability in multi-agent systems
- interaction between communication and control
- robustness of consensus under realistic delays

---

## Roadmap

### Done

- Log-normal AR(1) latency model (CORRELATED)
- Correct calibration (mean-preserving log transform)
- Round-trip validation pipeline
- Regime-switching latency (burst modeling)
- Basic multi-agent consensus simulation
- Quality report tool with explicit verdicts

### In progress

- Parameter fitting from real datasets (automated pipeline)
- Improved regime calibration (matching burst length distributions, fixing long-range ACF overshoot)

### Planned

- Queue-based congestion model (load → latency dynamics)
- ROS2 integration
- Zenoh backend support
- Phase transition detection tools

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