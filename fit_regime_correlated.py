"""
Grid search for REGIME_CORRELATED parameters.

Given target statistics (from a real latency trace's fit.json), searches
over REGIME_CORRELATED parameters and returns the configuration that
best matches the target by a weighted sum of relative errors in:
  - mean
  - std
  - p95
  - p99
  - burst_mean_length

Usage:
    python fit_regime_correlated.py <target_fit_json> [--trials 2000]
                                                       [--n-samples 20000]
                                                       [--link 0,1]

The target fit.json is the output of analyze_latency.py on a real trace.
We read the per-link stats from it and try to match them.
"""

import argparse
import json
import sys

import numpy as np

from temporis.fit import simulate_regime, stats_of


def score(observed, target, weights):
    """Weighted sum of relative errors, lower is better."""
    total = 0.0
    for key, w in weights.items():
        t = target[key]
        o = observed[key]
        if t == 0:
            err = abs(o)
        else:
            err = abs(o - t) / abs(t)
        total += w * err
    return total


def random_config(rng):
    """Sample a plausible REGIME_CORRELATED config.

    Ranges chosen to cover behaviors from "boring gaussian-ish" to
    "heavy bursty". If target is outside this envelope, widen by hand.
    """
    return {
        "rho": rng.uniform(0.60, 0.95),
        "normal_mean": rng.uniform(0.05, 0.15),
        "congested_mean": rng.uniform(0.25, 0.80),
        "normal_innovation_std": rng.uniform(0.05, 0.25),
        "congested_innovation_std": rng.uniform(0.10, 0.40),
        "p_nc": 10 ** rng.uniform(-4, -1),  # log-uniform 1e-4..1e-1
        "p_cn": 10 ** rng.uniform(-2, -0.3),  # log-uniform 1e-2..0.5
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("target", help="path to target fit.json (real data)")
    p.add_argument("--trials", type=int, default=2000)
    p.add_argument("--n-samples", type=int, default=20000,
                   help="trace length per trial")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--top", type=int, default=5,
                   help="how many best configs to print")
    args = p.parse_args()

    with open(args.target) as f:
        target_json = json.load(f)

    link = target_json.get("per_link") or {}
    link_stats = link.get("stats") or {}
    link_bursts = link.get("bursts") or {}
    if not link_stats:
        print("ERROR: target fit.json has no per_link.stats")
        sys.exit(1)

    target = {
        "mean": link_stats["mean"],
        "std": link_stats["std"],
        "p95": link_stats["p95"],
        "p99": link_stats["p99"],
        "burst_mean_len": link_bursts.get("mean_length", 0.0),
    }

    print("Target statistics (from", args.target, "):")
    for k, v in target.items():
        print(f"  {k:<16} = {v:.4f}")
    print()

    # Weights: burst_mean_len matters a lot because it's the temporal
    # structure metric; p99 matters because it captures tail behavior.
    weights = {
        "mean": 1.0,
        "std": 1.0,
        "p95": 1.5,
        "p99": 2.0,
        "burst_mean_len": 2.5,
    }

    rng = np.random.default_rng(args.seed)
    results = []

    for trial in range(args.trials):
        cfg = random_config(rng)
        trace = simulate_regime(N=args.n_samples, seed=trial + 1, **cfg)
        if trace is None:
            continue
        obs = stats_of(trace)
        s = score(obs, target, weights)
        results.append((s, cfg, obs))

        if (trial + 1) % max(1, args.trials // 10) == 0:
            best_so_far = min(r[0] for r in results)
            print(f"  trial {trial+1}/{args.trials}  best score = {best_so_far:.4f}")

    results.sort(key=lambda r: r[0])

    print(f"\n=== Top {args.top} configurations ===\n")
    for i, (s, cfg, obs) in enumerate(results[:args.top]):
        print(f"--- Rank {i+1}  score={s:.4f} ---")
        print(f"  config:")
        for k, v in cfg.items():
            print(f"    {k:<26} = {v:.6f}")
        print(f"  observed stats:")
        for k in ["mean", "std", "p95", "p99", "burst_mean_len"]:
            t = target[k]
            o = obs[k]
            rel = 100 * (o - t) / t if t != 0 else 0
            print(f"    {k:<16} = {o:.4f}   (target {t:.4f},  {rel:+.1f}%)")
        print()

    print("=== Best config as config.json latency block ===\n")
    best = results[0][1]
    print('"latency": {')
    print(f'  "rho": {best["rho"]:.6f},')
    print(f'  "normal_mean": {best["normal_mean"]:.6f},')
    print(f'  "congested_mean": {best["congested_mean"]:.6f},')
    print(f'  "normal_innovation_std": {best["normal_innovation_std"]:.6f},')
    print(f'  "congested_innovation_std": {best["congested_innovation_std"]:.6f},')
    print(f'  "p_normal_to_congested": {best["p_nc"]:.6f},')
    print(f'  "p_congested_to_normal": {best["p_cn"]:.6f}')
    print('}')


if __name__ == "__main__":
    main()
