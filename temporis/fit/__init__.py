"""
Shared fit utilities for Temporis.

Contains statistical helpers and AR(1) / log-AR(1) fit routines used by
both `analyze_latency.py` (per-trace analysis) and
`fit_regime_correlated.py` (grid search over regime-switching params).

No CLI, no plotting, no I/O. Pure functions on numpy arrays.
"""

import numpy as np


# =========================
# STATISTICAL HELPERS
# =========================

def compute_acf(x, max_lag=50):
    """Biased ACF estimator -- matches numpy/statsmodels with adjusted=False.

    Same formula as the C++ side, so values should be directly comparable.
    """
    x = np.asarray(x, dtype=float)
    x = x - np.mean(x)
    n = len(x)
    var = np.var(x)
    if var < 1e-12 or n < 2:
        return np.zeros(max_lag + 1)

    out = np.empty(max_lag + 1)
    out[0] = 1.0
    for lag in range(1, max_lag + 1):
        if lag >= n:
            out[lag] = 0.0
            continue
        out[lag] = np.sum(x[lag:] * x[:-lag]) / (n * var)
    return out


def compute_bursts(x, threshold):
    """Run-length of consecutive samples strictly above threshold."""
    bursts = []
    current = 0
    for v in x:
        if v > threshold:
            current += 1
        else:
            if current > 0:
                bursts.append(current)
                current = 0
    if current > 0:
        bursts.append(current)
    return bursts


def robust_stats(x):
    """Mean/std plus median/IQR/p95/p99 -- robust to heavy tails."""
    x = np.asarray(x, dtype=float)
    return {
        "n": int(len(x)),
        "mean": float(np.mean(x)),
        "std": float(np.std(x, ddof=1)) if len(x) > 1 else 0.0,
        "median": float(np.median(x)),
        "iqr": float(np.percentile(x, 75) - np.percentile(x, 25)),
        "p95": float(np.percentile(x, 95)),
        "p99": float(np.percentile(x, 99)),
        "min": float(np.min(x)),
        "max": float(np.max(x)),
    }


def stats_of(trace):
    """Compact summary used for regime-search scoring.

    Returns mean, std, p95, p99 and burst statistics (threshold = p95).
    This is the function `fit_regime_correlated.py` calls to evaluate each
    candidate configuration.
    """
    p95 = float(np.percentile(trace, 95))
    bursts = compute_bursts(trace, p95)
    return {
        "mean": float(np.mean(trace)),
        "std": float(np.std(trace, ddof=1)),
        "p95": p95,
        "p99": float(np.percentile(trace, 99)),
        "burst_mean_len": float(np.mean(bursts)) if bursts else 0.0,
        "burst_max_len": int(max(bursts)) if bursts else 0,
    }


# =========================
# AR(1) FITS
# =========================

def fit_ar1_linear(x):
    """Fit AR(1) directly on x: x_t = mu + rho * (x_{t-1} - mu) + eps_t.

    For NAIVE_CORRELATED mode in Temporis. Will be biased on real latency
    data because real latencies are non-negative and the gaussian AR(1)
    can't represent that without clamping.
    """
    x = np.asarray(x, dtype=float)
    if len(x) < 2:
        return None
    mu = float(np.mean(x))
    sigma = float(np.std(x, ddof=1))
    rho = float(np.corrcoef(x[:-1], x[1:])[0, 1])
    rho = max(-0.999, min(0.999, rho))
    sigma_eps = float(sigma * np.sqrt(1.0 - rho ** 2))
    return {
        "mu": mu,
        "sigma": sigma,
        "rho": rho,
        "sigma_eps": sigma_eps,
        "n": int(len(x)),
    }


def fit_ar1_log(x):
    """Fit AR(1) on log(x): log(x_t) = m + rho * (log(x_{t-1}) - m) + eps_t.

    For CORRELATED (log-normal) mode in Temporis. This is the preferred
    fit because the C++ model works in log-space internally and calibrates
    base_delay so that E[exp(y)] == base_delay in stationarity.
    """
    x = np.asarray(x, dtype=float)
    x = x[x > 0]  # log undefined for non-positive
    if len(x) < 2:
        return None

    log_x = np.log(x)
    log_mu = float(np.mean(log_x))
    log_sigma = float(np.std(log_x, ddof=1))
    rho = float(np.corrcoef(log_x[:-1], log_x[1:])[0, 1])
    rho = max(-0.999, min(0.999, rho))
    innovation_std = float(log_sigma * np.sqrt(1.0 - rho ** 2))
    # Recover base_delay so that E[exp(y)] == base_delay
    base_delay = float(np.exp(log_mu + 0.5 * log_sigma ** 2))
    return {
        "base_delay": base_delay,
        "rho": rho,
        "innovation_std": innovation_std,
        "log_mu": log_mu,
        "log_sigma": log_sigma,
        "n": int(len(x)),
    }


# =========================
# REGIME_CORRELATED SIMULATION
# =========================

def simulate_regime(N, rho, normal_mean, congested_mean,
                    normal_innovation_std, congested_innovation_std,
                    p_nc, p_cn, seed):
    """Simulate REGIME_CORRELATED using the exact same math as the C++ model.

    Markov-switching log-normal AR(1) with two states (NORMAL, CONGESTED),
    each with its own innovation_std; log_mean is compensated per-regime so
    that the stationary conditional mean equals the regime target.

    Returns a numpy array of length N, or None if rho is degenerate.
    """
    rng = np.random.default_rng(seed)
    denom = 1.0 - rho * rho
    if denom <= 1e-12:
        return None

    def log_mean_for(regime, inn_std):
        stat_std = inn_std / np.sqrt(denom)
        m = normal_mean if regime == 0 else congested_mean
        return np.log(m) - 0.5 * stat_std * stat_std

    stat_std_n = normal_innovation_std / np.sqrt(denom)
    log_state = rng.normal(log_mean_for(0, normal_innovation_std), stat_std_n)
    regime = 0

    trace = np.empty(N)
    for i in range(N):
        if regime == 0:
            if rng.uniform() < p_nc:
                regime = 1
        else:
            if rng.uniform() < p_cn:
                regime = 0
        inn_std = normal_innovation_std if regime == 0 else congested_innovation_std
        lm = log_mean_for(regime, inn_std)
        new_log = lm + rho * (log_state - lm) + rng.normal(0, inn_std)
        log_state = new_log
        trace[i] = np.exp(new_log)
    return trace


def simulate_correlated(N, base_delay, rho, innovation_std, seed):
    """Simulate CORRELATED (single-regime log-normal AR(1)).

    Same math as the C++ CORRELATED model:
      log_mean is compensated so that E[exp(y)] == base_delay
      log_state is initialized from the stationary distribution

    Returns a numpy array of length N, or None if rho is degenerate.
    """
    rng = np.random.default_rng(seed)
    denom = 1.0 - rho * rho
    if denom <= 1e-12:
        return None
    stat_log_std = innovation_std / np.sqrt(denom)
    log_mean = np.log(base_delay) - 0.5 * stat_log_std * stat_log_std
    log_state = rng.normal(log_mean, stat_log_std)
    trace = np.empty(N)
    for i in range(N):
        log_state = log_mean + rho * (log_state - log_mean) + rng.normal(0, innovation_std)
        trace[i] = np.exp(log_state)
    return trace