import pandas as pd
import matplotlib.pyplot as plt
import os
import sys

def load_run(run_path):
    system_path = os.path.join(run_path, "system.csv")
    network_path = os.path.join(run_path, "network.csv")

    system = pd.read_csv(system_path)
    network = pd.read_csv(network_path)

    return system, network


def plot_single(run_path):
    system, network = load_run(run_path)

    t = system["t"]
    print(system, network)
    # --- 1. Variance 
    plt.figure()
    plt.plot(t, system["var"])
    plt.xlabel("t")
    plt.ylabel("variance")
    plt.title("Consensus convergence")
    plt.grid()
    print("Saving to:", os.path.join(run_path, "variance.png"))

    plt.savefig(os.path.join(run_path, "variance.png"))
    print("Saved")

    # --- 2. Latency
    plt.figure()
    plt.plot(network["t"], network["mean_latency"])
    plt.xlabel("t")
    plt.ylabel("mean latency")
    plt.title("Network latency")
    plt.grid()
    plt.savefig(os.path.join(run_path, "latency.png"))

    # --- 3. Latency vs Variance
    plt.figure()
    plt.plot(network["mean_latency"], system["var"])
    plt.xlabel("mean latency")
    plt.ylabel("variance")
    plt.title("Latency vs convergence")
    plt.grid()
    plt.savefig(os.path.join(run_path, "latency_vs_variance.png"))

    print(f"Plots saved in {run_path}")


def plot_compare(run_paths, labels):
    plt.figure()

    for run_path, label in zip(run_paths, labels):
        system, _ = load_run(run_path)
        plt.plot(system["t"], system["var"], label=label)

    plt.xlabel("t")
    plt.ylabel("variance")
    plt.title("Comparison of delay models")
    plt.legend()
    plt.grid()
    plt.savefig("comparison.png")

    print("Comparison plot saved as comparison.png")


if __name__ == "__main__":
    print(len(sys.argv))
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python plot_results.py <run_folder>")
        print("  python plot_results.py compare <run1> <run2> ...")
        sys.exit(1)

    if sys.argv[1] == "compare":
        run_paths = [os.path.abspath(p) for p in sys.argv[2:]]
        labels = [os.path.basename(p) for p in run_paths]
        plot_compare(run_paths, labels)
    else:
        run_path = os.path.abspath(sys.argv[1])
        print("Using path:", run_path)
        plot_single(run_path)