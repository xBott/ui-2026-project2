import argparse

import pandas as pd

import compare

SEEDS_FROM = 1001
RUNS = compare.OUT / "experiment"
CSV = compare.OUT / "experiment.csv"

BEST = compare.CONFIGURATIONS["tuned"]

CONFIGURATIONS: dict[str, tuple[str, dict]] = {
    "default": ("default", compare.CONFIGURATIONS["baseline"]),
    "best": ("best", BEST),
    "best_find_best": ("best + find-best", {**BEST, "find_best": True}),
}

def main():
    parser = argparse.ArgumentParser(description="Run the best configuration from compare.py on new seeds.")
    parser.add_argument("--seeds", type=int, default=100, help="seeds per configuration")
    args = parser.parse_args()

    seeds = range(SEEDS_FROM, SEEDS_FROM + args.seeds)
    compare.run_configurations({name: settings for name, (_, settings) in CONFIGURATIONS.items()}, seeds, RUNS)

    frames = [pd.read_csv(RUNS / f"{name}.csv").assign(configuration=label) for name, (label, _) in CONFIGURATIONS.items()]
    pd.concat(frames).to_csv(CSV, index=False)

    table = compare.plot_all(CSV, ["configuration"], compare.PLOTS)
    (compare.OUT / "experiment.txt").write_text(table + "\n", encoding="utf-8")
    print(f"\n{table}\n\nTable in {compare.OUT}/experiment.txt, graphs in {compare.PLOTS}/")

if __name__ == "__main__":
    main()
