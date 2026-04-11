import os
import numpy as np
import pandas as pd
from tqdm import tqdm


def parse_dataset(input_dir, output_path, max_delay=5.0):

    all_rows = []

    files = sorted([
        f for f in os.listdir(input_dir)
        if f.startswith("SeattleData_")
    ], key=lambda x: int(x.split("_")[-1]))

    print(f"Found {len(files)} files")

    for t_idx, fname in enumerate(tqdm(files)):
        path = os.path.join(input_dir, fname)

        try:
            mat = np.loadtxt(path)
        except Exception as e:
            print(f"Skipping {fname}: {e}")
            continue

        N = mat.shape[0]

        for i in range(N):
            for j in range(N):
                if i == j:
                    continue

                rtt = mat[i, j]

                # --- cleaning ---
                if rtt <= 0 or np.isnan(rtt):
                    continue

                delay = rtt / 2.0  # RTT → one-way

                if delay > max_delay:
                    continue

                all_rows.append([t_idx, i, j, delay])

    df = pd.DataFrame(all_rows, columns=["t", "sender", "receiver", "delay"])

    print(f"Total samples: {len(df)}")

    df.to_csv(output_path, index=False)
    print(f"Saved to {output_path}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python parse_seattle.py <input_dir> <output_csv>")
        exit(1)

    input_dir = sys.argv[1]
    output_csv = sys.argv[2]

    parse_dataset(input_dir, output_csv)