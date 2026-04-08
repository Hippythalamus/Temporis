#pragma once

struct LatencyParams {
public:
    // ===== Shared across modes =====
    double normal_mean;
    double congested_mean;

    double normal_std;
    double congested_std;

    double congestion_threshold;  // used by the legacy REGIME mode only

    // ===== CORRELATED (log-normal AR(1)) =====
    // AR(1) innovation std in log-space (sigma_eps of log(latency)).
    // The stationary log-space std is innovation_std / sqrt(1 - rho^2).
    // When fitting from real data: innovation_std = log_std * sqrt(1 - rho^2).
    double innovation_std;
    double rho;

    // Stationary mean of the latency process. CORRELATED mode calibrates
    //   log_mean = log(base_delay) - 0.5 * stationary_log_std^2
    // so that E[latency] == base_delay in stationarity.
    double base_delay;

    // ===== REGIME_CORRELATED (Markov-switching log-normal AR(1)) =====
    // Separate log-space innovation std per regime. If you want them equal,
    // just set both to the same value -- but having two lets you model
    // "bursts are noisier", which is typically what real data shows.
    double normal_innovation_std;
    double congested_innovation_std;

    // Markov transition probabilities (per-sample, NOT load-dependent).
    // Expected dwell time in regime X is 1 / p_leave_X samples.
    // Example: p_normal_to_congested=0.001, p_congested_to_normal=0.05
    //   -> expected ~1000 samples in normal, ~20 in congested
    //   -> stationary share of congested ~ 0.001 / (0.001 + 0.05) ~ 2%
    double p_normal_to_congested;
    double p_congested_to_normal;

    // ===== Legacy / unused by the new modes =====
    double bandwidth;
    double packet_size;
};