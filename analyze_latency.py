"""
Latency trace analysis for Temporis.

Reads a latency.csv produced by consensus_demo and computes:
  - population statistics over all (sender, receiver) pairs
  - per-link analysis for a chosen pair (default 0 -> 1)
  - Two AR(1) fits:
      * linear AR(1)    -> for NAIVE_CORRELATED mode
      * log-normal AR(1) -> for CORRELATED mode (preferred)

Usage:
    python analyze_latency.py <latency_csv> <output_dir> [--link 0,1]
                                                          [--max-delay 5.0]
                                                          [--burst-percentile 95]
"""

import argparse
import json
import os
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


from temporis.fit import (
    compute_acf,
    compute_bursts,
    robust_stats,
    fit_ar1_linear,
    fit_ar1_log,
)

sys.path.insert(0, '.')
# =========================
# POPULATION ANALYSIS (all links)
# =========================

def analyze_population(df, out_dir):
    """Statistics across ALL (sender, receiver) pairs."""
    print(f"\n=== POPULATION (all links) ===")
    print(f"Total samples: {len(df)}")

    stats = robust_stats(df["delay"].values)
    print(f"  mean={stats['mean']:.4f}  std={stats['std']:.4f}")
    print(f"  median={stats['median']:.4f}  IQR={stats['iqr']:.4f}")
    print(f"  p95={stats['p95']:.4f}  p99={stats['p99']:.4f}")

    # ---- 1. CDF over all samples ----
    lat = df["delay"].values
    if len(lat) > 200_000:
        rng = np.random.default_rng(0)
        idx = rng.choice(len(lat), size=200_000, replace=False)
        lat = lat[idx]

    sorted_vals = np.sort(lat)
    cdf = np.arange(1, len(sorted_vals) + 1) / len(sorted_vals)

    plt.figure()
    plt.plot(sorted_vals, cdf)
    plt.xlabel("latency")
    plt.ylabel("CDF")
    plt.title(f"Latency CDF (all links, n={len(lat)})")
    plt.grid()
    plt.savefig(os.path.join(out_dir, "cdf_population.png"))
    plt.close()

    # ---- 2. Mean/var over time, averaged across pairs ----
    by_t = df.groupby("t")["delay"]
    mean_t = by_t.mean()
    var_t = by_t.var()

    plt.figure()
    plt.plot(mean_t.index, mean_t.values)
    plt.xlabel("t")
    plt.ylabel("mean latency (averaged across pairs)")
    plt.title("Mean latency over time")
    plt.grid()
    plt.savefig(os.path.join(out_dir, "mean_latency_population.png"))
    plt.close()

    plt.figure()
    plt.plot(var_t.index, var_t.values)
    plt.xlabel("t")
    plt.ylabel("variance across pairs")
    plt.title("Cross-link latency variance over time")
    plt.grid()
    plt.savefig(os.path.join(out_dir, "var_latency_population.png"))
    plt.close()

    return stats


# =========================
# PER-LINK ANALYSIS
# =========================

def analyze_link(df, sender, receiver, out_dir, burst_percentile=95):
    """Detailed analysis of a single (sender, receiver) trace."""
    print(f"\n=== LINK {sender} -> {receiver} ===")

    # Don't sort by t! In older CSVs, the `t` column may be delivery_time,
    # not send_time, and sorting by delivery_time reorders the series
    # because fast messages overtake slow ones. We rely on the C++ side
    # writing rows in send order (which it does, inside the nested
    # for-loop over agents). Use CSV row order as the ground truth.
    link = df[(df["sender"] == sender) & (df["receiver"] == receiver)]

    # Sanity check: is `t` monotonic within the link? If not, the CSV is
    # from an older run that logged delivery_time, and AR(1) estimates
    # will be slightly off (rho biased down, innovation_std biased up).
    t_vals = link["t"].values
    non_monotonic = int(np.sum(t_vals[1:] < t_vals[:-1]))
    if non_monotonic > 0:
        pct = 100.0 * non_monotonic / max(1, len(t_vals) - 1)
        print(f"  WARNING: {non_monotonic} non-monotonic timestamps "
              f"({pct:.1f}%) in link trace.")
        print(f"  This CSV likely logs delivery_time instead of send_time.")
        print(f"  AR(1) fit will have a slight downward bias on rho.")
        print(f"  Fix: update consensus_demo.cpp to log `time` (send),")
        print(f"       not `m.delivery_time`, in logger.log_latency(...).")
    if len(link) < 50:
        print(f"  not enough samples for link {sender}->{receiver} ({len(link)})")
        return None

    trace = link["delay"].values
    print(f"  samples: {len(trace)}")

    # ---- Robust stats ----
    stats = robust_stats(trace)
    print(f"  mean={stats['mean']:.4f}  std={stats['std']:.4f}")
    print(f"  median={stats['median']:.4f}  IQR={stats['iqr']:.4f}")
    print(f"  p95={stats['p95']:.4f}  p99={stats['p99']:.4f}")

    # ---- Single-link trace plot ----
    plt.figure()
    plt.plot(link["t"].values, trace)
    plt.xlabel("time")
    plt.ylabel("delay")
    plt.title(f"Single-link trace ({sender}->{receiver})")
    plt.grid()
    plt.savefig(os.path.join(out_dir, f"link_{sender}_{receiver}_trace.png"))
    plt.close()

    # ---- ACF ----
    acf_vals = compute_acf(trace, max_lag=50)

    plt.figure()
    plt.stem(range(len(acf_vals)), acf_vals)
    plt.axhline(0, color="k", lw=0.5)
    band = 1.96 / np.sqrt(len(trace))
    plt.axhline(band, color="r", lw=0.5, ls="--")
    plt.axhline(-band, color="r", lw=0.5, ls="--")
    plt.xlabel("lag")
    plt.ylabel("ACF")
    plt.title(f"Autocorrelation (link {sender}->{receiver})")
    plt.grid()
    plt.savefig(os.path.join(out_dir, f"link_{sender}_{receiver}_acf.png"))
    plt.close()

    print(f"  ACF lag1 (biased): {acf_vals[1]:.4f}")

    # ---- Both AR(1) fits ----
    fit_lin = fit_ar1_linear(trace)
    fit_log = fit_ar1_log(trace)

    if fit_lin is not None:
        print(f"  linear AR(1)    : mu={fit_lin['mu']:.4f}  "
              f"sigma={fit_lin['sigma']:.4f}  rho={fit_lin['rho']:.4f}  "
              f"sigma_eps={fit_lin['sigma_eps']:.4f}")
    if fit_log is not None:
        print(f"  log-normal AR(1): log_mu={fit_log['log_mu']:.4f}  "
              f"log_sigma={fit_log['log_sigma']:.4f}  "
              f"rho={fit_log['rho']:.4f}  "
              f"innovation_std={fit_log['innovation_std']:.4f}")

    # ---- Bursts ----
    threshold = float(np.percentile(trace, burst_percentile))
    bursts = compute_bursts(trace, threshold)

    burst_stats = None
    if bursts:
        burst_stats = {
            "threshold": threshold,
            "percentile": burst_percentile,
            "count": len(bursts),
            "mean_length": float(np.mean(bursts)),
            "max_length": int(np.max(bursts)),
        }
        print(f"  bursts (>p{burst_percentile}={threshold:.4f}): "
              f"count={len(bursts)}  mean_len={burst_stats['mean_length']:.2f}  "
              f"max_len={burst_stats['max_length']}")

        plt.figure()
        plt.hist(bursts, bins=min(50, len(bursts)))
        plt.xlabel("burst length")
        plt.ylabel("count")
        plt.title(f"Burst length distribution (link {sender}->{receiver}, "
                  f"threshold p{burst_percentile})")
        plt.grid()
        plt.savefig(os.path.join(out_dir, f"link_{sender}_{receiver}_bursts.png"))
        plt.close()
    else:
        print(f"  no bursts above p{burst_percentile}")

    return {
        "link": [sender, receiver],
        "stats": stats,
        "ar1_fit_linear": fit_lin,
        "ar1_fit_log": fit_log,
        "acf_lag1": float(acf_vals[1]),
        "bursts": burst_stats,
    }


# =========================
# ENTRY POINT
# =========================

def main():
    p = argparse.ArgumentParser()
    p.add_argument("csv", help="path to latency.csv")
    p.add_argument("out_dir", help="output directory for plots/fit.json")
    p.add_argument("--link", default="0,1",
                   help="sender,receiver pair for per-link analysis (default 0,1)")
    p.add_argument("--max-delay", type=float, default=None,
                   help="drop samples with delay > this (default: keep all)")
    p.add_argument("--burst-percentile", type=float, default=95.0,
                   help="percentile threshold for burst detection (default 95)")
    args = p.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    df = pd.read_csv(args.csv)
    print(f"Loaded {len(df)} rows from {args.csv}")

    link = df[(df.sender==0) & (df.receiver==1)].sort_values('t')
    dt_real = link['t'].diff().dropna()
    print(f"median dt: {dt_real.median()}, mean dt: {dt_real.mean()}")

    n0 = len(df)
    df = df[df["delay"] > 0]
    n_dropped_neg = n0 - len(df)
    if n_dropped_neg:
        print(f"  dropped {n_dropped_neg} samples with delay <= 0")

    if args.max_delay is not None:
        n1 = len(df)
        df = df[df["delay"] < args.max_delay]
        n_dropped_max = n1 - len(df)
        if n_dropped_max:
            pct = 100.0 * n_dropped_max / n1
            print(f"  dropped {n_dropped_max} samples ({pct:.2f}%) "
                  f"with delay >= {args.max_delay}")
            if pct > 1.0:
                print(f"  WARNING: dropping >1% of data -- you may be "
                      f"truncating a heavy tail that matters for CORRELATED.")

    pop_stats = analyze_population(df, args.out_dir)

    sender, receiver = (int(x) for x in args.link.split(","))
    link_result = analyze_link(df, sender, receiver, args.out_dir,
                               burst_percentile=args.burst_percentile)

    out = {
        "source_csv": args.csv,
        "n_samples_total": int(len(df)),
        "population": pop_stats,
        "per_link": link_result,
    }
    fit_path = os.path.join(args.out_dir, "fit.json")
    with open(fit_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {fit_path}")

    if link_result is not None:
        fit_log = link_result["ar1_fit_log"]
        fit_lin = link_result["ar1_fit_linear"]

        if fit_log is not None:
            print("\nFor Temporis CORRELATED mode (preferred, log-normal AR(1)):")
            print(f"  base_delay     : {fit_log['base_delay']:.6f}")
            print(f"  rho            : {fit_log['rho']:.6f}")
            print(f"  innovation_std : {fit_log['innovation_std']:.6f}")

        if fit_lin is not None:
            print("\nFor Temporis NAIVE_CORRELATED mode (gaussian AR(1) baseline):")
            print(f"  base_delay     : {fit_lin['mu']:.6f}")
            print(f"  rho            : {fit_lin['rho']:.6f}")
            print(f"  innovation_std : {fit_lin['sigma_eps']:.6f}")
            if fit_lin["mu"] < 2.0 * fit_lin["sigma"]:
                ratio = fit_lin["mu"] / fit_lin["sigma"]
                print(f"  NOTE: mu/sigma = {ratio:.2f} < 2.0 -- NAIVE_CORRELATED")
                print(f"        will distort the process via clamping at 0.")
                print(f"        Use CORRELATED mode for these parameters.")


if __name__ == "__main__":
    main()