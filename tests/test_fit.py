"""
Tests for temporis.fit shared module.

Run with:  python -m pytest tests/test_fit.py -v
Or:        python tests/test_fit.py
"""

import numpy as np
import sys
import os

# Allow running from repo root without installing temporis as a package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from temporis.fit import (
    compute_acf,
    compute_bursts,
    fit_ar1_linear,
    fit_ar1_log,
    robust_stats,
    simulate_correlated,
    simulate_regime,
    stats_of,
)


# =========================
# 1. Round-trip: CORRELATED
# =========================

def test_roundtrip_correlated():
    """Known params -> simulate -> fit -> recovered params match input.

    This is the most important test. If it fails, either simulate_correlated
    or fit_ar1_log has a bug. Tolerance is generous (5%) because traces are
    finite (n=10000) and there is inherent sampling variance.
    """
    true_params = {
        "base_delay": 0.13,
        "rho": 0.81,
        "innovation_std": 0.40,
    }

    recovered = {"base_delay": [], "rho": [], "innovation_std": []}
    seeds = [10, 20, 30, 40, 50]

    for seed in seeds:
        trace = simulate_correlated(N=10000, seed=seed, **true_params)
        assert trace is not None, "simulate_correlated returned None"
        assert len(trace) == 10000
        assert np.all(trace > 0), "log-normal trace must be strictly positive"

        fit = fit_ar1_log(trace)
        assert fit is not None, "fit_ar1_log returned None"
        recovered["base_delay"].append(fit["base_delay"])
        recovered["rho"].append(fit["rho"])
        recovered["innovation_std"].append(fit["innovation_std"])

    for key in true_params:
        median_val = float(np.median(recovered[key]))
        target = true_params[key]
        rel_err = abs(median_val - target) / target
        assert rel_err < 0.05, (
            f"Round-trip failed for {key}: "
            f"target={target}, median recovered={median_val:.4f}, "
            f"rel_err={rel_err:.1%}"
        )


# =========================
# 2. Fit on constant trace
# =========================

def test_fit_on_constant():
    """Constant trace should not crash and should give rho near zero."""
    trace = np.full(500, 0.15)
    fit = fit_ar1_log(trace)
    # All values identical -> log(trace) is constant -> std=0 -> rho undefined.
    # fit_ar1_log should handle this gracefully (not crash, not return NaN).
    # With ddof=1 and identical values, std is 0, corrcoef returns NaN,
    # and rho gets clamped to [-0.999, 0.999]. Accept any finite result.
    if fit is not None:
        assert np.isfinite(fit["rho"]), "rho should be finite on constant trace"
        assert np.isfinite(fit["base_delay"]), "base_delay should be finite"

    fit_lin = fit_ar1_linear(trace)
    if fit_lin is not None:
        assert np.isfinite(fit_lin["rho"]), "linear rho should be finite"


# =========================
# 3. Round-trip: REGIME_CORRELATED (marginal check)
# =========================

def test_roundtrip_regime():
    """Simulate regime -> stats_of -> marginal stats in expected range.

    No inverse fit exists for regime, so we check that the generated trace
    has marginal statistics broadly consistent with the input parameters.
    """
    params = {
        "rho": 0.91,
        "normal_mean": 0.095,
        "congested_mean": 0.35,
        "normal_innovation_std": 0.11,
        "congested_innovation_std": 0.17,
        "p_nc": 0.004,
        "p_cn": 0.025,
    }

    means = []
    for seed in [1, 2, 3, 4, 5]:
        trace = simulate_regime(N=20000, seed=seed, **params)
        assert trace is not None
        assert len(trace) == 20000
        assert np.all(trace > 0)
        s = stats_of(trace)
        means.append(s["mean"])
        # Basic sanity: mean should be between normal_mean and congested_mean
        assert s["mean"] > params["normal_mean"] * 0.5, (
            f"mean too low: {s['mean']}"
        )
        assert s["mean"] < params["congested_mean"] * 3.0, (
            f"mean too high: {s['mean']}"
        )
        assert s["std"] > 0, "std should be positive"
        assert s["p95"] > s["mean"], "p95 should exceed mean"

    # Median mean across seeds should be roughly between the two regime means
    median_mean = float(np.median(means))
    assert params["normal_mean"] * 0.8 < median_mean < params["congested_mean"] * 1.5, (
        f"median mean {median_mean} outside expected range"
    )


# =========================
# 4. compute_bursts (deterministic)
# =========================

def test_compute_bursts():
    """Deterministic input -> exact burst lengths."""
    # Trace: 5 values above threshold 0.5, then 3 below, then 2 above
    x = [0.6, 0.7, 0.8, 0.6, 0.9,   0.1, 0.2, 0.3,   0.7, 0.6]
    bursts = compute_bursts(x, threshold=0.5)
    assert bursts == [5, 2], f"Expected [5, 2], got {bursts}"

    # All below threshold -> no bursts
    assert compute_bursts([0.1, 0.2, 0.3], 0.5) == []

    # All above threshold -> one burst of full length
    assert compute_bursts([0.6, 0.7, 0.8], 0.5) == [3]

    # Empty input
    assert compute_bursts([], 0.5) == []


# =========================
# 5. compute_acf on white noise
# =========================

def test_compute_acf_white_noise():
    """White noise should have ACF near zero for lag > 0."""
    rng = np.random.default_rng(42)
    x = rng.standard_normal(10000)
    acf = compute_acf(x, max_lag=30)

    assert acf[0] == 1.0, "ACF at lag 0 must be 1.0"

    # For n=10000, 95% confidence band is about 1.96/sqrt(10000) ~ 0.02.
    # Allow a generous 0.05 to avoid flaky tests.
    for lag in range(1, 31):
        assert abs(acf[lag]) < 0.05, (
            f"ACF at lag {lag} = {acf[lag]:.4f}, expected near zero for white noise"
        )


# =========================
# Runner (for non-pytest usage)
# =========================

if __name__ == "__main__":
    tests = [
        test_compute_bursts,
        test_compute_acf_white_noise,
        test_fit_on_constant,
        test_roundtrip_correlated,
        test_roundtrip_regime,
    ]
    failed = 0
    for t in tests:
        name = t.__name__
        try:
            t()
            print(f"  PASS  {name}")
        except Exception as e:
            print(f"  FAIL  {name}: {e}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)