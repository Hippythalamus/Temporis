#pragma once
#include <map>
#include <random>
#include <cstdint>
#include "LatencyModel.hpp"
#include "LatencyModelParams.hpp"

class RegimeLatencyModel : public LatencyModel {
public:
    enum class Regime { NORMAL, CONGESTED };
    enum class Mode {
        NO_DELAY,
        IID,
        IID_EXPONENTIAL,
        REGIME,              // legacy: gaussian with global regime switching
        NAIVE_CORRELATED,    // gaussian AR(1) with max(0, .) clamping
        CORRELATED,          // log-normal AR(1), single regime -- validated baseline
        REGIME_CORRELATED,    // Markov-switching log-normal AR(1), per-link state
        QUEUE,
        ZENOH_QUEUE
    };

    RegimeLatencyModel(Mode mode, const LatencyParams& latency, uint64_t seed = 2);

    double sample(int sender, int receiver, double t, int network_load, int queue_size) override;

private:
    Regime regime_;  // used only by legacy REGIME mode
    Mode mode_;

    double normal_mean_;
    double congested_mean_;

    double normal_std_;
    double congested_std_;

    double congestion_threshold_;

    double innovation_std_;
    double rho_;
    double base_delay_;
    double bandwidth_;
    double packet_size_;

    // REGIME_CORRELATED-specific
    double normal_innovation_std_;
    double congested_innovation_std_;
    double p_normal_to_congested_;
    double p_congested_to_normal_;

    // Per-link state for AR(1) modes.
    // For CORRELATED and REGIME_CORRELATED, log_state is log(latency) of the
    // last sample on that link. initialized=false means we haven't sampled
    // from this link yet, so sample() should draw from the stationary
    // distribution on first use. regime is 0 (NORMAL) or 1 (CONGESTED),
    // used only by REGIME_CORRELATED.
    struct LinkState {
        bool initialized = false;
        double log_state = 0.0;
        int regime = 0;
    };
    std::map<std::pair<int,int>, LinkState> prev_state_;

    // NAIVE_CORRELATED uses linear-space state; we keep it in a separate map
    // so there's no risk of interpretation mismatch.
    std::map<std::pair<int,int>, double> prev_linear_state_;

    std::mt19937 rng_;

    // Legacy REGIME mode helpers
    double regime_switch_prob(int network_load);
    void update_regime(int network_load);
};