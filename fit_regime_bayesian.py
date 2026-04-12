"""
Bayesian optimization for REGIME_CORRELATED parameters using Optuna.

Replaces the random grid search in fit_regime_correlated.py with a smarter
search that uses past trials to guide future ones. Also supports two loss
functions: v1 (marginals + burst, same as the old grid search) and v2
(marginals + burst + ACF terms, designed to fix the long-range correlation
overshoot we observed in baseline diagnostics).

Usage:
    python fit_regime_bayesian.py <target_fit_json> \
        --target-csv <real_data_csv> \
        --trials 500 \
        --n-samples 30000 \
        --loss v2 \
        --save-config best_regime.json \
        [--report-progress]

Output:
    Prints best config and observed stats. If --save-config is given, writes
    a JSON file in the format expected by temporis_report.py --regime-config
    (same shape as the `latency` block in Temporis config.json).

Requires:
    pip install optuna
"""

import argparse
import json
import sys

import numpy as np
import pandas as pd

try:
    import optuna
except ImportError:
    print("ERROR: optuna is not installed. Run: pip install optuna")
    sys.exit(1)

from temporis.fit import (
    compute_acf,
    simulate_regime,
    stats_of,
)


# =========================
# LOSS FUNCTIONS
# =========================

def loss_v1(observed, target_marg, target_burst):
    """Original loss: marginals + burst mean length only.

    Identical to fit_regime_correlated.py for direct comparison between
    grid search and Bayesian optimization on the same criterion.
    """
    weights = {
        "mean": 1.0,
        "std": 1.0,
        "p95": 1.5,
        "p99": 2.0,
        "burst_mean_len": 2.5,
    }
    total = 0.0
    for key, w in weights.items():
        if key == "burst_mean_len":
            t = target_burst
        else:
            t = target_marg[key]
        o = observed[key]
        err = abs(o - t) / abs(t) if t else abs(o)
        total += w * err
    return total


def loss_v2(observed, target_marg, target_burst, observed_acf, target_acf):
    """Loss v1 + ACF mismatch penalties at lags 1, 5, 10.

    Lag 5 is heavily weighted because baseline diagnostics show it as the
    largest individual mismatch (target ~0.10, baseline sim ~0.81).
    """
    base = loss_v1(observed, target_marg, target_burst)
    acf_penalty = (
        3.0 * abs(observed_acf[1] - target_acf[1])
        + 3.0 * abs(observed_acf[5] - target_acf[5])
        + 2.0 * abs(observed_acf[10] - target_acf[10])
    )
    return base + acf_penalty


def loss_v3(observed, target_marg, target_burst, observed_acf, target_acf,
            burst_count):
    """Burst-heavy / ACF-light counterweight to v2.

    Fixed degenerate corner: configs that produce zero bursts (model never
    reaches target threshold) get a hard penalty, and burst length error
    is absolute instead of relative to avoid divide-by-near-zero behavior
    when the optimizer collapses bursts to zero.
    """
    # Hard penalty for collapsed configs (no bursts at all).
    if burst_count == 0:
        return 1e6

    weights = {
        "mean": 1.0,
        "std": 1.5,
        "p95": 1.5,
        "p99": 2.0,
    }
    total = 0.0
    for key, w in weights.items():
        t = target_marg[key]
        o = observed[key]
        err = abs(o - t) / abs(t) if t else abs(o)
        total += w * err

    # Burst length: absolute error (not relative). Coefficient 1.0 here
    # corresponds roughly to weight 5.0 in the relative-error scale, since
    # target_burst ~ 5.8.
    total += 1.0 * abs(observed["burst_mean_len"] - target_burst)

    acf_penalty = (
        1.5 * abs(observed_acf[1] - target_acf[1])
        + 1.5 * abs(observed_acf[5] - target_acf[5])
        + 1.0 * abs(observed_acf[10] - target_acf[10])
    )
    return total + acf_penalty


# =========================
# OBJECTIVE FOR OPTUNA
# =========================

def make_objective(target_marg, target_burst, target_acf, n_samples,
                   loss_version):
    """Build a closure with all targets baked in. Optuna passes a Trial."""

    def objective(trial):
        # Search space matches fit_regime_correlated.random_config ranges,
        # but using optuna's smarter sampling.
        rho = trial.suggest_float("rho", 0.60, 0.95)
        normal_mean = trial.suggest_float("normal_mean", 0.05, 0.15)
        congested_mean = trial.suggest_float("congested_mean", 0.25, 0.80)
        normal_innovation_std = trial.suggest_float(
            "normal_innovation_std", 0.05, 0.25)
        congested_innovation_std = trial.suggest_float(
            "congested_innovation_std", 0.10, 0.40)
        # log-uniform priors for transition probabilities (matches old script)
        p_nc = trial.suggest_float("p_nc", 1e-4, 1e-1, log=True)
        p_cn = trial.suggest_float("p_cn", 1e-2, 0.5, log=True)

        # Use trial.number as seed for reproducibility within a single
        # Optuna study. Different studies will start from seed=0 and explore
        # different points.
        trace = simulate_regime(
            N=n_samples,
            rho=rho,
            normal_mean=normal_mean,
            congested_mean=congested_mean,
            normal_innovation_std=normal_innovation_std,
            congested_innovation_std=congested_innovation_std,
            p_nc=p_nc,
            p_cn=p_cn,
            seed=trial.number + 1,
        )
        if trace is None:
            # Degenerate rho: tell Optuna to ignore this trial.
            raise optuna.TrialPruned()

        observed = stats_of(trace)

        if loss_version == "v1":
            return loss_v1(observed, target_marg, target_burst)
        elif loss_version == "v2":
            observed_acf = compute_acf(trace, max_lag=10)
            return loss_v2(observed, target_marg, target_burst,
                           observed_acf, target_acf)
        else:  # v3
            observed_acf = compute_acf(trace, max_lag=10)
            # Need burst count to detect degenerate configs
            from temporis.fit import compute_bursts
            bursts = compute_bursts(trace, target_marg["p95"])
            return loss_v3(observed, target_marg, target_burst,
                           observed_acf, target_acf, len(bursts))

    return objective


# =========================
# I/O
# =========================

def load_targets(fit_json_path, target_csv_path):
    """Load target marginal/burst from fit.json and target ACF from CSV."""
    with open(fit_json_path) as f:
        fit_json = json.load(f)
    link = fit_json["per_link"]
    link_stats = link["stats"]
    link_bursts = link.get("bursts") or {}

    target_marg = {
        "mean": link_stats["mean"],
        "std": link_stats["std"],
        "p95": link_stats["p95"],
        "p99": link_stats["p99"],
    }
    target_burst = float(link_bursts.get("mean_length", 0.0)) or 1e-9

    # ACF from raw CSV
    df = pd.read_csv(target_csv_path)
    df = df[(df["sender"] == link["link"][0]) &
            (df["receiver"] == link["link"][1])]
    df = df[df["delay"] > 0]
    target_trace = df["delay"].values
    target_acf = compute_acf(target_trace, max_lag=10)

    return target_marg, target_burst, target_acf, len(target_trace)


def save_regime_config(path, params):
    """Write best regime config in the format temporis_report.py expects.

    Renames p_nc -> p_normal_to_congested and p_cn -> p_congested_to_normal
    so the file matches the `latency` block of Temporis config.json.
    """
    out = {
        "rho": params["rho"],
        "normal_mean": params["normal_mean"],
        "congested_mean": params["congested_mean"],
        "normal_innovation_std": params["normal_innovation_std"],
        "congested_innovation_std": params["congested_innovation_std"],
        "p_normal_to_congested": params["p_nc"],
        "p_congested_to_normal": params["p_cn"],
    }
    with open(path, "w") as f:
        json.dump(out, f, indent=2)


# =========================
# MAIN
# =========================

def main():
    p = argparse.ArgumentParser()
    p.add_argument("fit_json", help="path to fit.json (target stats)")
    p.add_argument("--target-csv", required=True,
                   help="raw real-data CSV (needed for target ACF)")
    p.add_argument("--trials", type=int, default=500)
    p.add_argument("--n-samples", type=int, default=30000)
    p.add_argument("--loss", choices=["v1", "v2", "v3"], default="v2",
                   help="v1 = marginals+burst (baseline grid-search criterion). "
                        "v2 = v1 + ACF penalty at lags 1,5,10 (default; "
                        "fits ACF at the cost of burst length). "
                        "v3 = burst-heavy / ACF-light counterweight to v2 "
                        "(maps a third point on the Pareto frontier).")
    p.add_argument("--save-config", default=None,
                   help="write best regime config to this JSON file")
    p.add_argument("--report-progress", action="store_true",
                   help="print best loss every 50 trials")
    p.add_argument("--seed", type=int, default=0,
                   help="seed for Optuna sampler")
    args = p.parse_args()

    print(f"Loading targets from {args.fit_json} and {args.target_csv}...")
    target_marg, target_burst, target_acf, n_target = load_targets(
        args.fit_json, args.target_csv)

    print(f"Target trace length: {n_target}")
    print(f"Target marginal: mean={target_marg['mean']:.4f}, "
          f"std={target_marg['std']:.4f}, "
          f"p95={target_marg['p95']:.4f}, p99={target_marg['p99']:.4f}")
    print(f"Target burst mean length: {target_burst:.4f}")
    print(f"Target ACF: lag1={target_acf[1]:.3f}, lag5={target_acf[5]:.3f}, "
          f"lag10={target_acf[10]:.3f}")
    print(f"Loss version: {args.loss}")
    print(f"Trials: {args.trials}, n_samples per trial: {args.n_samples}")
    print()

    objective = make_objective(target_marg, target_burst, target_acf,
                               args.n_samples, args.loss)

    sampler = optuna.samplers.TPESampler(seed=args.seed)
    study = optuna.create_study(direction="minimize", sampler=sampler)

    # Suppress optuna's per-trial logging unless user explicitly asked
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    if args.report_progress:
        def progress_callback(study, trial):
            if (trial.number + 1) % 50 == 0:
                print(f"  trial {trial.number + 1}/{args.trials}  "
                      f"best loss = {study.best_value:.4f}")
        callbacks = [progress_callback]
    else:
        callbacks = []

    study.optimize(objective, n_trials=args.trials, callbacks=callbacks,
                   show_progress_bar=False)

    best = study.best_params
    best_loss = study.best_value

    # Re-evaluate best config to print observed stats
    trace = simulate_regime(
        N=args.n_samples,
        seed=study.best_trial.number + 1,
        **best,
    )
    obs = stats_of(trace)
    obs_acf = compute_acf(trace, max_lag=10)

    print(f"\n=== Best configuration (loss = {best_loss:.4f}) ===\n")
    print("Parameters:")
    for k in ["rho", "normal_mean", "congested_mean",
              "normal_innovation_std", "congested_innovation_std",
              "p_nc", "p_cn"]:
        print(f"  {k:<26} = {best[k]:.6f}")

    print("\nObserved vs target:")
    print(f"  {'stat':<18} {'target':>10} {'observed':>10} {'rel err':>10}")
    for k in ["mean", "std", "p95", "p99"]:
        t = target_marg[k]
        o = obs[k]
        rel = 100 * (o - t) / t if t else 0
        print(f"  {k:<18} {t:>10.4f} {o:>10.4f} {rel:>+9.1f}%")
    t = target_burst
    o = obs["burst_mean_len"]
    rel = 100 * (o - t) / t if t else 0
    print(f"  {'burst_mean_len':<18} {t:>10.4f} {o:>10.4f} {rel:>+9.1f}%")

    print("\nACF comparison:")
    print(f"  {'lag':<6} {'target':>10} {'observed':>10} {'abs diff':>10}")
    for lag in [1, 5, 10]:
        t = target_acf[lag]
        o = obs_acf[lag]
        print(f"  {lag:<6} {t:>10.3f} {o:>10.3f} {abs(o-t):>10.3f}")

    if args.save_config:
        save_regime_config(args.save_config, best)
        print(f"\nWrote {args.save_config}")
        print(f"Now run: python3 temporis_report.py {args.fit_json} "
              f"--mode regime --regime-config {args.save_config} "
              f"--output report_optuna.md")


if __name__ == "__main__":
    main()