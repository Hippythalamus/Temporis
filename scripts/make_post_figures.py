"""
Generate publication-ready plots for the Temporis blog post.

Inputs (CSVs in standard latency format: t,sender,receiver,delay):
  --real     path to real data CSV (e.g. Seattle)
  --corr     path to CORRELATED simulation CSV
  --regime   path to REGIME_CORRELATED simulation CSV

Outputs (PNG files in --out dir):
  fig1_roundtrip.png        - round-trip parameter recovery (target vs observed)
  fig2_cdf_comparison.png   - CDF Seattle vs CORRELATED vs REGIME
  fig3_trace_comparison.png - single-link trace, all three side-by-side
  fig4_acf_comparison.png   - autocorrelation function, all three on same axes
  fig5_burst_comparison.png - burst length distribution, all three
"""

import argparse
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# --- consistent styling ---
plt.rcParams.update({
    "figure.dpi": 110,
    "savefig.dpi": 150,
    "font.size": 11,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "axes.spines.top": False,
    "axes.spines.right": False,
})

COLOR_REAL = "#222222"        # near-black for real data
COLOR_CORR = "#1f77b4"        # blue for CORRELATED
COLOR_REGIME = "#d62728"      # red for REGIME_CORRELATED
COLOR_TARGET = "#888888"      # grey reference lines


def load_link(path, sender=0, receiver=1):
    df = pd.read_csv(path)
    df = df[df["delay"] > 0]
    link = df[(df["sender"] == sender) & (df["receiver"] == receiver)]
    return link["delay"].values


def compute_acf(x, max_lag=30):
    x = np.asarray(x, dtype=float) - np.mean(x)
    n = len(x)
    var = np.var(x)
    if var < 1e-12:
        return np.zeros(max_lag + 1)
    out = np.empty(max_lag + 1)
    out[0] = 1.0
    for lag in range(1, max_lag + 1):
        if lag >= n:
            out[lag] = 0.0
        else:
            out[lag] = np.sum(x[lag:] * x[:-lag]) / (n * var)
    return out


def compute_bursts(x, threshold):
    bursts, cur = [], 0
    for v in x:
        if v > threshold:
            cur += 1
        else:
            if cur > 0:
                bursts.append(cur)
            cur = 0
    if cur > 0:
        bursts.append(cur)
    return bursts


def fig1_roundtrip(out_path):
    """Round-trip validation: target vs observed for the 3 AR(1) params."""
    # Hardcoded numbers from the actual 5-seed CORRELATED runs.
    # These don't depend on input CSVs because the round-trip is the
    # *check* that the model recovers what you put in.
    params = ["base_delay", "rho", "innovation_std"]
    targets = [0.12855, 0.80969, 0.40421]
    observed_median = [0.12591, 0.81152, 0.40272]
    observed_min = [0.12272, 0.80444, 0.39810]
    observed_max = [0.13175, 0.81901, 0.40562]

    fig, axes = plt.subplots(1, 3, figsize=(11, 3.6))
    for ax, p, t, m, lo, hi in zip(axes, params, targets, observed_median,
                                    observed_min, observed_max):
        # error bar around median
        err_lo = m - lo
        err_hi = hi - m
        ax.errorbar([0.5], [m], yerr=[[err_lo], [err_hi]],
                    fmt="o", color=COLOR_CORR, capsize=6,
                    markersize=10, label="observed (5 seeds)")
        ax.axhline(t, color=COLOR_TARGET, linestyle="--", linewidth=1.5,
                   label="Seattle target")
        ax.set_xlim(0, 1)
        ax.set_xticks([])
        ax.set_title(p, fontsize=11)
        rel = 100 * (m - t) / t
        ax.text(0.5, 0.02, f"{rel:+.1f}%", transform=ax.transAxes,
                ha="center", fontsize=10, color="#555")
        # widen y-range a bit
        span = max(hi - lo, abs(t) * 0.05)
        center = (m + t) / 2
        ax.set_ylim(center - span * 1.5, center + span * 1.5)

    axes[0].legend(loc="upper left", fontsize=9, frameon=False)
    fig.suptitle("Round-trip parameter recovery (CORRELATED, 5 seeds)",
                 fontsize=12, y=1.02)
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight")
    plt.close()
    print(f"  wrote {out_path}")


def fig2_cdf(real, corr, regime, out_path):
    """CDF comparison: real vs CORRELATED vs REGIME_CORRELATED."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))

    for data, name, color in [(real, "Seattle (real)", COLOR_REAL),
                              (corr, "CORRELATED", COLOR_CORR),
                              (regime, "REGIME_CORRELATED", COLOR_REGIME)]:
        s = np.sort(data)
        c = np.arange(1, len(s) + 1) / len(s)
        ax1.plot(s, c, label=name, color=color, linewidth=1.8)
        ax2.plot(s, 1 - c, label=name, color=color, linewidth=1.8)

    ax1.set_xlabel("latency (s)")
    ax1.set_ylabel("CDF")
    ax1.set_title("Distribution body")
    ax1.set_xlim(0, max(np.percentile(real, 99.5), 0.6))
    ax1.legend(loc="lower right", fontsize=9, frameon=False)

    ax2.set_xlabel("latency (s)")
    ax2.set_ylabel("1 - CDF (log scale)")
    ax2.set_title("Tail (log scale)")
    ax2.set_yscale("log")
    ax2.set_xlim(0, max(np.percentile(real, 99.9), 1.0))
    ax2.set_ylim(1e-4, 1)
    ax2.legend(loc="upper right", fontsize=9, frameon=False)

    fig.suptitle("Latency distribution: real vs simulated", fontsize=12, y=1.02)
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight")
    plt.close()
    print(f"  wrote {out_path}")


def fig3_traces(real, corr, regime, out_path, n_show=688):
    """Single-link trace, three subplots stacked."""
    fig, axes = plt.subplots(3, 1, figsize=(11, 6.5), sharex=True, sharey=True)

    for ax, data, name, color in zip(
            axes,
            [real, corr[:n_show], regime[:n_show]],
            ["Seattle (real)", "CORRELATED (sim)", "REGIME_CORRELATED (sim)"],
            [COLOR_REAL, COLOR_CORR, COLOR_REGIME]):
        ax.plot(np.arange(len(data)), data, color=color, linewidth=0.9)
        ax.set_ylabel(f"{name}\nlatency (s)", fontsize=10)
        # mark p95 of real data as horizontal reference
        p95 = np.percentile(real, 95)
        ax.axhline(p95, color=COLOR_TARGET, linestyle=":", linewidth=1)

    axes[-1].set_xlabel("time slice")
    # auto y-range from real, since traces shown at same length should be
    # visually comparable
    ymax = max(np.percentile(real, 99.5),
               np.percentile(corr[:n_show], 99.5),
               np.percentile(regime[:n_show], 99.5)) * 1.1
    for ax in axes:
        ax.set_ylim(0, ymax)

    fig.suptitle(f"Single-link trace (first {n_show} samples)",
                 fontsize=12, y=1.0)
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight")
    plt.close()
    print(f"  wrote {out_path}")


def fig4_acf(real, corr, regime, out_path):
    """Autocorrelation function comparison."""
    max_lag = 30
    fig, ax = plt.subplots(1, 1, figsize=(8, 4.5))

    for data, name, color, marker in [
            (real, "Seattle (real)", COLOR_REAL, "o"),
            (corr, "CORRELATED", COLOR_CORR, "s"),
            (regime, "REGIME_CORRELATED", COLOR_REGIME, "^")]:
        acf = compute_acf(data, max_lag=max_lag)
        ax.plot(np.arange(max_lag + 1), acf, marker=marker, markersize=4,
                color=color, label=name, linewidth=1.4)

    ax.axhline(0, color="black", linewidth=0.5)
    ax.set_xlabel("lag")
    ax.set_ylabel("ACF")
    ax.set_title("Autocorrelation function: real vs simulated")
    ax.legend(loc="upper right", fontsize=10, frameon=False)
    ax.set_xlim(0, max_lag)
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight")
    plt.close()
    print(f"  wrote {out_path}")


def fig5_bursts(real, corr, regime, out_path):
    """Burst length distribution: histogram comparison.

    Uses density normalization so Seattle (only ~6 bursts) is visible
    next to CORRELATED (~165 bursts).
    """
    fig, ax = plt.subplots(1, 1, figsize=(8, 4.5))

    # Use real p95 as the burst threshold for all three (fair comparison)
    threshold = np.percentile(real, 95)

    for data, name, color in [
            (real, "Seattle (real)", COLOR_REAL),
            (corr, "CORRELATED", COLOR_CORR),
            (regime, "REGIME_CORRELATED", COLOR_REGIME)]:
        bursts = compute_bursts(data, threshold)
        if not bursts:
            continue
        max_b = max(bursts)
        bins = np.arange(0.5, max(max_b, 15) + 1.5, 1)
        ax.hist(bursts, bins=bins, alpha=0.55, color=color, density=True,
                label=f"{name} (n={len(bursts)}, mean={np.mean(bursts):.1f})",
                edgecolor=color, linewidth=1.0)

    ax.set_xlabel(f"burst length (consecutive samples > {threshold:.3f})")
    ax.set_ylabel("density")
    ax.set_title("Burst length distribution (density-normalized)")
    ax.legend(loc="upper right", fontsize=9, frameon=False)
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight")
    plt.close()
    print(f"  wrote {out_path}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--real", required=True, help="real data CSV (e.g. Seattle)")
    p.add_argument("--corr", required=True, help="CORRELATED sim CSV")
    p.add_argument("--regime", required=True, help="REGIME_CORRELATED sim CSV")
    p.add_argument("--out", default="post_figures",
                   help="output directory")
    p.add_argument("--link", default="0,1",
                   help="sender,receiver pair (default 0,1)")
    args = p.parse_args()

    os.makedirs(args.out, exist_ok=True)
    sender, receiver = (int(x) for x in args.link.split(","))

    print("Loading traces...")
    real = load_link(args.real, sender, receiver)
    corr = load_link(args.corr, sender, receiver)
    regime = load_link(args.regime, sender, receiver)
    print(f"  real:   {len(real)} samples")
    print(f"  corr:   {len(corr)} samples")
    print(f"  regime: {len(regime)} samples")

    print("\nGenerating figures...")
    fig1_roundtrip(os.path.join(args.out, "fig1_roundtrip.png"))
    fig2_cdf(real, corr, regime, os.path.join(args.out, "fig2_cdf_comparison.png"))
    fig3_traces(real, corr, regime, os.path.join(args.out, "fig3_trace_comparison.png"),
                n_show=min(688, len(real)))
    fig4_acf(real, corr, regime, os.path.join(args.out, "fig4_acf_comparison.png"))
    fig5_bursts(real, corr, regime, os.path.join(args.out, "fig5_burst_comparison.png"))

    print(f"\nAll figures written to {args.out}/")


if __name__ == "__main__":
    main()