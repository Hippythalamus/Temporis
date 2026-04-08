# Temporis  
**Structured latency as a first-class experimental variable**

Temporis is a framework for simulating **time-dependent, stochastic network latency** and studying how it affects multi-agent system behavior.

Unlike traditional tools, Temporis treats latency not as noise — but as a **dynamic process with structure, memory, and regimes**.

---

## Why this matters

Most simulations assume latency is:
- constant  
- or IID noise  

But real systems don’t behave like that.

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

Same average latency. Completely different outcomes:

| Model              | Behavior |
|-------------------|----------|
| IID               | stable convergence |
| CORRELATED        | slow drift |
| REGIME_CORRELATED | oscillations / instability |

The difference is not magnitude — it’s **temporal structure**.

---

## Build

mkdir build
cd build
cmake ..
make


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

###  In progress

- Parameter fitting from real datasets (automated pipeline)  
- Improved regime calibration (matching burst length distributions)  

###  Planned

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