# Temporis
Structured latency injection framework for studying multi-agent system stability.

It enables controlled manipulation of communication latency as a stochastic, time-dependent process to study its impact on system-level behavior such as consensus, coordination, and stability.

---

## Motivation

Most existing tools treat latency as a measurable property or a simple random variable.

In contrast, **Temporis** treats latency as a **controllable dynamic process**:

- not just delay magnitude, but delay *structure*
- not just measurement, but *intervention*
- not just networking, but *system-level effects*

---

##  Key Idea

> System stability is not determined by average latency, but by the **temporal structure of latency processes**.

Temporis enables experiments where:
- identical mean latency produces different system behavior
- bursty or correlated delays lead to instability
- latency acts as a control parameter

---

## Features

- Stochastic latency models:
  - IID (Gaussian, Uniform)
  - Regime-switching (bursty latency)
  - Load-dependent latency

- Discrete-event network simulation:
  - delayed message delivery
  - configurable latency processes

- Multi-agent simulation:
  - consensus (included)
  - extensible to formation / task allocation

---

## Architecture

- `LatencyModel`: defines temporal delay behavior
- `NetworkSimulator`: schedules message delivery
- `Agents`: implement coordination logic
- `Experiment`: runs scenarios and collects metrics

---

##  Example: Consensus under structured latency

Temporis allows studying how different latency regimes affect convergence:

| Latency Model | Mean Delay | Behavior |
|--------------|-----------|----------|
| IID Gaussian | 100 ms    | Stable convergence |
| Bursty       | 100 ms    | Oscillations |
| Correlated   | 100 ms    | Drift / instability |

---

##  Build

mkdir build
cd build
cmake ..
make

##  Research Direction

Temporis is designed for studying:

1/ latency-induced phase transitions
2/ stability of multi-agent systems under communication uncertainty
3/ interaction between middleware and control algorithms

## Roadmap
 Correlated latency models
 Queue-based congestion model
 ROS2 integration layer
 Zenoh backend support
 Phase transition detection tools

## Contributing

Contributions are welcome, especially in:

new latency models
multi-agent scenarios
integration with real robotic systems 