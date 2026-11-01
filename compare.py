import argparse
import io
import os
import shutil
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from contextlib import redirect_stdout
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import plot
import project2
from project2 import MutationRates

GENERATIONS = 300
ROOT = Path(__file__).parent
OUT = ROOT / "experiments"
PLOTS = ROOT / "plots"

BASE = {"pop_size": 200}

NO_STRUCTURAL = MutationRates(swap=0.0, insert=0.0, delete=0.0)

CONFIGURATIONS: dict[str, dict] = {
    "baseline": {},
    "tournament": {"selector": "TOURNAMENT"},
    "tournament_2": {"selector": "TOURNAMENT", "tournament_size": 2},
    "tournament_5": {"selector": "TOURNAMENT", "tournament_size": 5},
    "two_point": {"crossover": "TWO_POINT"},
    "elite_0": {"elite": 0},
    "elite_10": {"elite": 10},
    "no_structural": {"mutation": NO_STRUCTURAL},
    "double_mutation": {"mutation": MutationRates(bit_flip=0.04, random_cell=0.02, invert=0.01)},
    "init_16": {"init_cells": 16},
    "wrap": {"wrap": True},
    "tuned": {"selector": "TOURNAMENT", "tournament_size": 5, "elite": 10, "mutation": NO_STRUCTURAL, "wrap": True},
}

COMPARISONS: dict[str, tuple[list[str], list[str]]] = {
    "selection": (["selection"], ["baseline", "tournament"]),
    "tournament_size": (["tournament_size"], ["tournament_2", "tournament", "tournament_5"]),
    "crossover": (["crossover"], ["baseline", "two_point"]),
    "elitism": (["elite"], ["elite_0", "baseline", "elite_10"]),
    "mutation": (["insert", "bit_flip"], ["baseline", "no_structural", "double_mutation"]),
    "initialization": (["init_cells"], ["init_16", "baseline"]),
    "memory_end": (["wrap"], ["baseline", "wrap"]),
    "tuned": (["selection", "elite", "insert", "wrap"], ["baseline", "tuned"]),
}

def run(task: tuple[dict, int, Path]):

    settings, seed, log = task
    sys.stdin = io.StringIO()
    with open(os.devnull, "w") as devnull, redirect_stdout(devnull):
        project2.main(**BASE, **settings, seed=seed, generations=GENERATIONS, delay=0, log_path=log)

def merge(parts: list[Path], target: Path):

    with target.open("w", encoding="utf-8") as out:
        for i, part in enumerate(parts):
            lines = part.read_text(encoding="utf-8").splitlines(keepends=True)
            out.writelines(lines if i == 0 else lines[1:])

def run_configurations(configurations: dict[str, dict], seeds: range, out: Path):

    tmp = Path(tempfile.mkdtemp())
    tasks = [(settings, seed, tmp / f"{name}_{seed}.csv") for name, settings in configurations.items() for seed in seeds]
    print(f"{len(configurations)} configurations x {len(seeds)} seeds = {len(tasks)} runs")

    started = time.perf_counter()
    with ProcessPoolExecutor() as pool:
        for i, _ in enumerate(pool.map(run, tasks, chunksize=4), 1):
            if i % 200 == 0 or i == len(tasks):
                print(f"  {i}/{len(tasks)} runs, {time.perf_counter() - started:.0f} s")

    out.mkdir(parents=True, exist_ok=True)
    for name in configurations:
        merge([tmp / f"{name}_{seed}.csv" for seed in seeds], out / f"{name}.csv")

    shutil.rmtree(tmp)

def plot_all(csv: Path, group: list[str], out: Path) -> str:

    df, runs = plot.load(csv, group)
    out.mkdir(parents=True, exist_ok=True)
    plot.plot_fitness(df, runs, out)
    plot.plot_success(runs, out)
    plot.plot_results(runs, out)
    plt.close("all")
    return plot.summary(runs).to_string()

def compare(name: str, group: list[str], configurations: list[str]):
    csv = OUT / f"{name}.csv"
    merge([OUT / "runs" / f"{c}.csv" for c in configurations], csv)

    table = plot_all(csv, group, PLOTS / name)
    (OUT / f"{name}.txt").write_text(table + "\n", encoding="utf-8")
    print(f"\n{name}\n{table}")

def main():
    parser = argparse.ArgumentParser(description="Compare the methods of project2.py against the default settings.")
    parser.add_argument("comparisons", nargs="*", metavar="comparison", help=f"comparisons to run (default: all of {', '.join(COMPARISONS)})")
    parser.add_argument("--seeds", type=int, default=100, help="seeds per configuration")
    args = parser.parse_args()

    unknown = [c for c in args.comparisons if c not in COMPARISONS]
    if unknown:
        parser.error(f"unknown comparison(s) {', '.join(unknown)}; choose from {', '.join(COMPARISONS)}")
    comparisons = args.comparisons or list(COMPARISONS)
    names = list(dict.fromkeys(c for comparison in comparisons for c in COMPARISONS[comparison][1]))

    run_configurations({n: CONFIGURATIONS[n] for n in names}, range(1, args.seeds + 1), OUT / "runs")
    for comparison in comparisons:
        compare(comparison, *COMPARISONS[comparison])
    print(f"\nTables in {OUT}/, graphs in {PLOTS}/<comparison>/")

if __name__ == "__main__":
    main()
