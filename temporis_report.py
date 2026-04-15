"""
Quality report for a fitted latency model.

Reads a fit.json (output of analyze_latency.py), runs round-trip validation
on the fitted parameters across multiple seeds, compares marginal/burst/ACF
statistics against the target, and emits a markdown report with verdicts.

Usage:
    python temporis_report.py <fit_json> --mode {correlated,regime} \
        --output report.md [--seeds 2,3,4,6,7] [--n-samples 6387]
        [--regime-config regime_config.json]

For mode=regime, you must pass --regime-config pointing to a JSON file
with the REGIME_CORRELATED parameters (the latency block from a Temporis
config.json, or the dict printed by fit_regime_correlated.py).
"""

import argparse
import json
import os

import matplotlib.pyplot as plt
import numpy as np

from temporis.fit import (
    compute_acf,
    compute_bursts,
    fit_ar1_log,
    robust_stats,
    simulate_correlated,
    simulate_regime,
)


# =========================
# CORE: round-trip + comparison across seeds
# =========================

def run_seeds(simulate_fn, n_samples, seeds):
    """Run simulate_fn for each seed, return list of traces."""
    traces = []
    for s in seeds:
        t = simulate_fn(n_samples, seed=s)
        if t is None:
            raise ValueError(f"simulate returned None for seed={s} (degenerate rho?)")
        traces.append(t)
    return traces


def median_with_range(values):
    """Return (median, min, max) for a list of floats."""
    arr = np.array(values, dtype=float)
    return float(np.median(arr)), float(np.min(arr)), float(np.max(arr))


def compare_marginal(target_stats, traces):
    """Per-trace marginal stats, then median+range across traces."""
    keys = ["mean", "std", "p95", "p99", "max"]
    per = [robust_stats(t) for t in traces]
    out = {}
    for k in keys:
        med, lo, hi = median_with_range([p[k] for p in per])
        t = target_stats[k]
        out[k] = {"target": t, "median": med, "min": lo, "max": hi,
                  "rel_err_pct": 100.0 * (med - t) / t if t else 0.0}
    return out


def compare_bursts(target_burst, traces, threshold):
    """Burst statistics under fixed (target) threshold for fair comparison."""
    counts, means, maxes = [], [], []
    for t in traces:
        b = compute_bursts(t, threshold)
        counts.append(len(b))
        means.append(float(np.mean(b)) if b else 0.0)
        maxes.append(int(max(b)) if b else 0)
    out = {}
    for label, vals, tgt_key in [("count", counts, "count"),
                                 ("mean_length", means, "mean_length"),
                                 ("max_length", maxes, "max_length")]:
        med, lo, hi = median_with_range(vals)
        t = target_burst.get(tgt_key, 0.0) or 0.0
        out[label] = {"target": t, "median": med, "min": lo, "max": hi,
                      "rel_err_pct": 100.0 * (med - t) / t if t else 0.0}
    return out


def compare_acf(target_trace, sim_traces, lags=(1, 5, 10, 30)):
    """ACF at selected lags: target vs median sim."""
    target_acf = compute_acf(target_trace, max_lag=max(lags))
    sim_acfs = [compute_acf(t, max_lag=max(lags)) for t in sim_traces]
    out = {}
    for lag in lags:
        sim_vals = [a[lag] for a in sim_acfs]
        med, lo, hi = median_with_range(sim_vals)
        t = float(target_acf[lag])
        out[lag] = {"target": t, "median": med, "min": lo, "max": hi,
                    "abs_diff": abs(med - t)}
    return out, target_acf, sim_acfs

def simulate_queue(arrival_times, bandwidth, packet_size, propagation_delay):
    """
    Deterministic M/D/1 queue simulation (sender-side, Step 1 model).
    Matches C++ QueueLatencyModel exactly (no noise, no randomness).
    """
    service_time = packet_size / bandwidth

    t_complete = 0.0
    delays = []

    for t_arr in arrival_times:
        t_start = max(t_arr, t_complete)
        t_complete = t_start + service_time
        delay = (t_complete - t_arr) + propagation_delay
        delays.append(delay)

    return np.array(delays)


# =========================
# ROUND-TRIP (only for CORRELATED -- the only mode where we have a clean
# inverse fit)
# =========================

def roundtrip_correlated(target_params, traces):
    """Refit log-AR(1) on each simulated trace, compare to input params."""
    fits = [fit_ar1_log(t) for t in traces]
    out = {}
    for key, target_key in [("base_delay", "base_delay"),
                            ("rho", "rho"),
                            ("innovation_std", "innovation_std")]:
        vals = [f[key] for f in fits if f is not None]
        med, lo, hi = median_with_range(vals)
        t = target_params[target_key]
        out[key] = {"target": t, "median": med, "min": lo, "max": hi,
                    "rel_err_pct": 100.0 * (med - t) / t if t else 0.0}
    return out


# =========================
# VERDICT (warnings)
# =========================

def build_verdict(report, mode, n_samples_target):
    """Return list of (level, message) where level in {ok, warn, fail}."""
    v = []

    if n_samples_target < 2000:
        v.append(("warn", f"Target trace is short (n={n_samples_target} < 2000); "
                          "burst statistics will have high seed-to-seed variance."))

    fit = report["fit_params"]
    rho = fit.get("rho", 0.0)
    if rho > 0.97:
        v.append(("warn", f"Fitted rho={rho:.4f} is near unit root; AR(1) may be unstable."))
    
    if mode == "queue":
        v.append(("ok", "Queue model evaluated on fixed arrival trace (deterministic)."))

    if mode == "correlated":
        rt = report["roundtrip"]
        for k in ["base_delay", "rho", "innovation_std"]:
            err = abs(rt[k]["rel_err_pct"])
            if err > 5.0:
                v.append(("fail", f"Round-trip {k} drift {err:.1f}% > 5% — check dt and scale matching."))
            else:
                v.append(("ok", f"Round-trip {k} drift {err:.1f}% within 5%."))

    marg = report["marginal"]
    std_err = abs(marg["std"]["rel_err_pct"])
    if std_err > 15.0:
        v.append(("fail", f"Marginal std mismatch {std_err:.1f}% > 15%."))
    else:
        v.append(("ok", f"Marginal std within 15% ({std_err:.1f}%)."))

    bursts = report["bursts"]
    blen_err = abs(bursts["mean_length"]["rel_err_pct"])
    if blen_err > 30.0:
        v.append(("warn", f"Burst mean length mismatch {blen_err:.1f}% > 30% — "
                          "consider regime-switching model." if mode == "correlated"
                          else f"Burst mean length mismatch {blen_err:.1f}% > 30%."))
    else:
        v.append(("ok", f"Burst mean length within 30% ({blen_err:.1f}%)."))

    acf = report["acf"]
    for lag in (10, 30):
        if lag in acf:
            d = acf[lag]["abs_diff"]
            if d > 0.2:
                v.append(("warn", f"ACF mismatch at lag {lag}: |sim-target|={d:.2f} > 0.2 — "
                                  "model overstates long-range correlation."))
            else:
                v.append(("ok", f"ACF at lag {lag} within 0.2 ({d:.2f})."))

    return v


# =========================
# MARKDOWN RENDERING
# =========================

def fmt_row(name, d, fmt="{:.4f}"):
    t = fmt.format(d["target"])
    m = fmt.format(d["median"])
    rng = f"[{fmt.format(d['min'])}, {fmt.format(d['max'])}]"
    err = f"{d['rel_err_pct']:+.1f}%"
    return f"| {name} | {t} | {m} | {rng} | {err} |"


def render_markdown(report, mode, source_csv, n_samples_target, seeds, fig_dir):
    L = []
    L.append(f"# Temporis fit quality report")
    L.append(f"")
    L.append(f"- **Source:** `{source_csv}`")
    L.append(f"- **Mode:** `{mode}`")
    L.append(f"- **Target trace length:** {n_samples_target} samples")
    L.append(f"- **Seeds used for sim:** {seeds}")
    L.append(f"")

    if mode == "correlated":
        L.append("## Round-trip parameter recovery")
        L.append("")
        L.append("| Parameter | Target | Median | Range | Error |")
        L.append("|---|---|---|---|---|")
        for k in ["base_delay", "rho", "innovation_std"]:
            L.append(fmt_row(k, report["roundtrip"][k]))
        L.append("")
        L.append(f"![round-trip]({fig_dir}/roundtrip.png)")
        L.append("")

    L.append("## Marginal statistics")
    L.append("")
    L.append("| Statistic | Target | Sim median | Range | Error |")
    L.append("|---|---|---|---|---|")
    for k in ["mean", "std", "p95", "p99", "max"]:
        L.append(fmt_row(k, report["marginal"][k]))
    L.append("")
    L.append(f"![cdf]({fig_dir}/cdf.png)")
    L.append("")

    L.append("## Burst statistics (threshold = target p95)")
    L.append("")
    L.append("| Statistic | Target | Sim median | Range | Error |")
    L.append("|---|---|---|---|---|")
    for k in ["count", "mean_length", "max_length"]:
        L.append(fmt_row(k, report["bursts"][k]))
    L.append("")

    L.append("## Autocorrelation function")
    L.append("")
    L.append("| Lag | Target ACF | Sim median | Range | |sim-target| |")
    L.append("|---|---|---|---|---|")
    for lag in sorted(report["acf"].keys()):
        d = report["acf"][lag]
        rng = f"[{d['min']:.3f}, {d['max']:.3f}]"
        L.append(f"| {lag} | {d['target']:.3f} | {d['median']:.3f} | {rng} | {d['abs_diff']:.3f} |")
    L.append("")
    L.append(f"![acf]({fig_dir}/acf.png)")
    L.append("")

    L.append("## Verdict")
    L.append("")
    for level, msg in report["verdict"]:
        icon = {"ok": "+", "warn": "?", "fail": "-"}[level]
        L.append(f"- {icon} {msg}")
    L.append("")
    return "\n".join(L)


# =========================
# PLOTS (3 figures next to report)
# =========================

def make_plots(report, target_trace, sim_traces, target_acf, sim_acfs,
               fig_dir, mode, show_seeds=False):
    """Generate three diagnostic plots.

    By default each sim is summarised as a median line plus a [min, max]
    envelope across seeds (clean and readable). Pass show_seeds=True to
    additionally overlay each individual seed as a thin translucent line --
    useful when you suspect outliers or multimodality across seeds.
    """
    os.makedirs(fig_dir, exist_ok=True)

    # ---- Round-trip (unchanged: error bars are already median+envelope) ----
    if mode == "correlated":
        rt = report["roundtrip"]
        fig, axes = plt.subplots(1, 3, figsize=(10, 3.4))
        for ax, k in zip(axes, ["base_delay", "rho", "innovation_std"]):
            d = rt[k]
            ax.errorbar([0.5], [d["median"]],
                        yerr=[[d["median"] - d["min"]], [d["max"] - d["median"]]],
                        fmt="o", color="#1f77b4", capsize=6, markersize=10,
                        label="sim median (5 seeds)")
            ax.axhline(d["target"], color="#888", linestyle="--", linewidth=1.5,
                       label="target")
            ax.set_xlim(0, 1); ax.set_xticks([])
            ax.set_title(k)
        axes[0].legend(loc="best", fontsize=8, frameon=False)
        plt.tight_layout()
        plt.savefig(os.path.join(fig_dir, "roundtrip.png"), dpi=120,
                    bbox_inches="tight")
        plt.close()

    # ---- CDF: target line + sim median + [min,max] envelope ----
    # Build a common x grid covering the union of all traces, then for each
    # x compute CDF_i(x) for each sim trace and reduce to median/min/max.
    x_max = max(np.percentile(target_trace, 99.5),
                max(np.percentile(t, 99.5) for t in sim_traces))
    x_grid = np.linspace(0, x_max, 400)
    sim_cdfs = np.empty((len(sim_traces), len(x_grid)))
    for i, t in enumerate(sim_traces):
        sorted_t = np.sort(t)
        sim_cdfs[i, :] = np.searchsorted(sorted_t, x_grid, side="right") / len(t)
    cdf_med = np.median(sim_cdfs, axis=0)
    cdf_lo = np.min(sim_cdfs, axis=0)
    cdf_hi = np.max(sim_cdfs, axis=0)

    target_sorted = np.sort(target_trace)
    target_cdf = np.arange(1, len(target_sorted) + 1) / len(target_sorted)

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(target_sorted, target_cdf, color="black", lw=1.8, label="target")
    ax.plot(x_grid, cdf_med, color="#1f77b4", lw=1.8,
            label=f"sim median ({len(sim_traces)} seeds)")
    ax.fill_between(x_grid, cdf_lo, cdf_hi, color="#1f77b4", alpha=0.20,
                    label="sim [min, max]")
    if show_seeds:
        for t in sim_traces:
            s = np.sort(t)
            ax.plot(s, np.arange(1, len(s) + 1) / len(s),
                    color="#1f77b4", alpha=0.35, lw=0.8)
    ax.set_xlim(0, x_max)
    ax.set_xlabel("latency"); ax.set_ylabel("CDF")
    ax.set_title("CDF: target vs simulated")
    ax.legend(loc="lower right", fontsize=9, frameon=False)
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(fig_dir, "cdf.png"), dpi=120, bbox_inches="tight")
    plt.close()

    # ---- ACF: target with markers + sim median + envelope ----
    max_lag = len(target_acf) - 1
    sim_acf_arr = np.array(sim_acfs)  # shape (n_seeds, max_lag+1)
    acf_med = np.median(sim_acf_arr, axis=0)
    acf_lo = np.min(sim_acf_arr, axis=0)
    acf_hi = np.max(sim_acf_arr, axis=0)
    lags = np.arange(max_lag + 1)

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(lags, target_acf, "o-", color="black", lw=1.8, ms=4, label="target")
    ax.plot(lags, acf_med, "s-", color="#1f77b4", lw=1.8, ms=4,
            label=f"sim median ({len(sim_traces)} seeds)")
    ax.fill_between(lags, acf_lo, acf_hi, color="#1f77b4", alpha=0.20,
                    label="sim [min, max]")
    if show_seeds:
        for a in sim_acfs:
            ax.plot(lags, a, color="#1f77b4", alpha=0.35, lw=0.8)
    ax.axhline(0, color="black", lw=0.5)
    ax.set_xlabel("lag"); ax.set_ylabel("ACF")
    ax.set_title("ACF: target vs simulated")
    ax.legend(loc="upper right", fontsize=9, frameon=False)
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(fig_dir, "acf.png"), dpi=120, bbox_inches="tight")
    plt.close()


# =========================
# ENTRY POINT
# =========================

def main():
    p = argparse.ArgumentParser()
    p.add_argument("fit_json", help="path to fit.json from analyze_latency.py")
    p.add_argument("--mode", choices=["correlated", "regime", "queue"], required=True)
    p.add_argument("--output", default="report.md")
    p.add_argument("--seeds", default="2,3,4,6,7")
    p.add_argument("--n-samples", type=int, default=None,
                   help="trace length per seed (default: same as target)")
    p.add_argument("--regime-config", default=None,
                   help="JSON with regime params (required for --mode regime)")
    p.add_argument("--target-csv", default=None,
                   help="raw CSV for ACF on target trace (default: source_csv from fit.json)")
    p.add_argument("--show-seeds", action="store_true",
                   help="overlay individual seeds as thin lines on CDF and ACF "
                        "plots in addition to the median+envelope summary")
    p.add_argument("--arrival-csv", default=None,
               help="CSV with arrival trace (required for --mode queue)")
    args = p.parse_args()

    with open(args.fit_json) as f:
        fit_json = json.load(f)
    link = fit_json["per_link"]
    target_stats = link["stats"]
    target_burst = link.get("bursts") or {}
    n_samples_target = target_stats["n"]
    n_samples = args.n_samples or n_samples_target
    seeds = [int(s) for s in args.seeds.split(",")]

    # Load target trace for ACF
    import pandas as pd
    src = args.target_csv or fit_json["source_csv"]
    df = pd.read_csv(src)
    df = df[(df["sender"] == link["link"][0]) & (df["receiver"] == link["link"][1])]
    df = df[df["delay"] > 0]
    target_trace = df["delay"].values

   # Build simulate function for chosen mode
    if args.mode == "correlated":
        fit_p = link["ar1_fit_log"]
        params = {
            "base_delay": fit_p["base_delay"],
            "rho": fit_p["rho"],
            "innovation_std": fit_p["innovation_std"]
        }
        sim_fn = lambda N, seed: simulate_correlated(N=N, seed=seed, **params)

    elif args.mode == "regime":
        if not args.regime_config:
            raise SystemExit("--regime-config required for --mode regime")

        with open(args.regime_config) as f:
            rc = json.load(f)
        if "latency" in rc:
            rc = rc["latency"]

        params = {
            "rho": rc["rho"],
            "normal_mean": rc["normal_mean"],
            "congested_mean": rc["congested_mean"],
            "normal_innovation_std": rc["normal_innovation_std"],
            "congested_innovation_std": rc["congested_innovation_std"],
            "p_nc": rc.get("p_normal_to_congested", rc.get("p_nc")),
            "p_cn": rc.get("p_congested_to_normal", rc.get("p_cn")),
        }

        sim_fn = lambda N, seed: simulate_regime(N=N, seed=seed, **params)

    elif args.mode == "queue":
        if not args.arrival_csv:
            raise SystemExit("--arrival-csv required for --mode queue")

        import pandas as pd

        df_arr = pd.read_csv(args.arrival_csv)
        link_pair = tuple(link["link"])

        df_arr = df_arr[
            (df_arr["sender"] == link_pair[0]) &
            (df_arr["receiver"] == link_pair[1])
        ]

        arrival_times = df_arr["t"].values

        if args.regime_config:
            with open(args.regime_config) as f:
                rc = json.load(f)
            if "latency" in rc:
                rc = rc["latency"]
        else:
            raise SystemExit("--regime-config required for --mode queue (for bandwidth params)")

        params = {

            "bandwidth": rc.get("bandwidth_mean", rc.get("bandwidth")),
            "packet_size": rc["packet_size"],
            "propagation_delay": rc["propagation_delay"],
        }

        sim_fn = lambda N, seed: simulate_queue(
            arrival_times=arrival_times,
            **params
        )

    if args.mode == "queue":
        print("Running queue simulation (deterministic, 1 trace)...")
        sim_traces = [sim_fn(None, None)]
    else:
        print(f"Running {len(seeds)} seeds, n_samples={n_samples}...")
        sim_traces = run_seeds(sim_fn, n_samples, seeds)

    threshold = float(np.percentile(target_trace, 95))
    if "threshold" not in target_burst:
        target_burst["threshold"] = threshold

    report = {
        "fit_params": params,
        "marginal": compare_marginal(target_stats, sim_traces),
        "bursts": compare_bursts(target_burst, sim_traces, threshold),
    }
    acf_cmp, target_acf, sim_acfs = compare_acf(target_trace, sim_traces)
    report["acf"] = acf_cmp
    if args.mode == "correlated":
        report["roundtrip"] = roundtrip_correlated(params, sim_traces)
    report["verdict"] = build_verdict(report, args.mode, n_samples_target)

    out_dir = os.path.dirname(os.path.abspath(args.output)) or "."
    fig_dir = os.path.join(out_dir, "report_figs")
    make_plots(report, target_trace, sim_traces, target_acf, sim_acfs,
               fig_dir, args.mode, show_seeds=args.show_seeds)

    md = render_markdown(report, args.mode, fit_json["source_csv"],
                         n_samples_target, seeds,
                         os.path.relpath(fig_dir, out_dir))
    with open(args.output, "w") as f:
        f.write(md)
    print(f"Wrote {args.output}")
    print(f"Figures in {fig_dir}/")


if __name__ == "__main__":
    main()