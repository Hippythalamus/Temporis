import pandas as pd
import matplotlib.pyplot as plt
import os
import sys

def load_run(run_path):
    system_path = os.path.join(run_path, "system.csv")
    network_path = os.path.join(run_path, "network.csv")
    latency_path = os.path.join(run_path, "latency.csv")

    system = pd.read_csv(system_path)
    network = pd.read_csv(network_path)
    latency = pd.read_csv(latency_path)

    return system, network, latency


def plot_cdf(latencies, save_path):
    import numpy as np

    lat = latencies

    if len(lat) > 100000:
        lat = lat.sample(100000)

    sorted_vals = np.sort(lat)
    cdf = np.arange(1, len(sorted_vals)+1) / len(sorted_vals)

    plt.figure()
    plt.plot(sorted_vals, cdf)
    plt.xlabel("latency")
    plt.ylabel("CDF")
    plt.title("Latency distribution")
    plt.grid()
    plt.savefig(save_path)
    plt.close()

def plot_single_link(latencies, save_path):
    import numpy as np

    df = latencies[(latencies["sender"]==0) & (latencies["receiver"]==1)]
    plt.figure()
    plt.plot(df["t"], df["delay"])
    plt.xlabel("time")
    plt.ylabel("Latency")
    plt.title("Single-Link Latency Trace (sender #0, receiver #1)")
    plt.grid()
    plt.savefig(save_path)
    plt.close()

def plot_acf(latencies, save_path, max_lag=50):
    import numpy as np

    x = latencies
    x = x - np.mean(x)

    acf = []
    for k in range(1, max_lag):
        num = np.sum(x[k:] * x[:-k])
        den = np.sum(x * x)
        acf.append(num / den)

    plt.figure()
    plt.plot(range(1, max_lag), acf)
    plt.xlabel("lag")
    plt.ylabel("ACF")
    plt.title("Autocorrelation")
    plt.grid()
    plt.savefig(save_path)
    plt.close()

def plot_queue_size(network, save_path):
    plt.figure()
    plt.plot(network["t"], network["queue_size"])
    plt.xlabel("t")
    plt.ylabel("queue size")
    plt.title("Queue dynamics")
    plt.grid()
    plt.savefig(save_path)
    plt.close()

def plot_single(run_path):
    system, network, latency = load_run(run_path)

    t = system["t"]
    print(system, network)
    # --- 1. Variance 
    plt.figure()
    plt.plot(t, system["var"])
    plt.xlabel("t")
    plt.ylabel("variance")
    plt.title("Consensus convergence")
    plt.grid()

    plt.savefig(os.path.join(run_path, "variance.png"))
    plt.close()

    # --- 2. Latency
    plt.figure()
    plt.plot(network["t"], network["mean_latency"])
    plt.xlabel("t")
    plt.ylabel("mean latency")
    plt.title("Network latency")
    plt.grid()
    plt.savefig(os.path.join(run_path, "latency.png"))
    plt.close()

    # --- 3. Latency vs Variance
    plt.figure()
    plt.plot(network["mean_latency"], system["var"])
    plt.xlabel("mean latency")
    plt.ylabel("variance")
    plt.title("Latency vs convergence")
    plt.grid()
    plt.savefig(os.path.join(run_path, "latency_vs_variance.png"))
    plt.close()

    # --- 4. CDF
    plot_cdf(latency["delay"], os.path.join(run_path, "cdf.png"))

    # ---- 5. Single-link Latency Trace
    plot_single_link(latency, os.path.join(run_path, "sllt.png"))

    # --- 6. ACF
    plot_acf(latency["delay"], os.path.join(run_path, "acf.png"), 150)

    # --- 7. Queue size(t)
    plot_queue_size(network, os.path.join(run_path, "queue.png"))

    print(f"Plots saved in {run_path}")


def plot_compare(run_paths, labels):
    plt.figure()

    for run_path, label in zip(run_paths, labels):
        system, _, _ = load_run(run_path)
        plt.plot(system["t"], system["var"], label=label)

    plt.xlabel("t")
    plt.ylabel("variance")
    plt.title("Comparison of delay models")
    plt.legend()
    plt.grid()
    plt.savefig("comparison.png")
    plt.close()

    print("Comparison plot saved as comparison.png")


if __name__ == "__main__":
    print(len(sys.argv))

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python plot_results.py <run_folder>")
        print("  python plot_results.py compare <run1> <run2> ...")
        print("  python plot_results.py all <parent_folder>")
        sys.exit(1)

    mode = sys.argv[1]

    if mode == "compare":
        run_paths = [os.path.abspath(p) for p in sys.argv[2:]]
        labels = [os.path.basename(p) for p in run_paths]
        plot_compare(run_paths, labels)

    elif mode == "all":
        if len(sys.argv) < 3:
            print("Usage: python plot_results.py all <parent_folder>")
            sys.exit(1)

        parent = os.path.abspath(sys.argv[2])
        print("Scanning:", parent)

        for name in os.listdir(parent):
            run_path = os.path.join(parent, name)

            if not os.path.isdir(run_path):
                continue

            if not os.path.exists(os.path.join(run_path, "system.csv")):
                continue

            print("Processing:", run_path)
            plot_single(run_path)

    else:
        run_path = os.path.abspath(sys.argv[1])
        print("Using path:", run_path)
        plot_single(run_path)