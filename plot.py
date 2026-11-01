import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from project2 import Grid

def load(path: Path, group: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:

    df = pd.read_csv(path)

    df["run"] = (df["generation"].diff() != 1).cumsum()
    parts = [df[c].astype(str) if pd.api.types.is_string_dtype(df[c]) else f"{c}=" + df[c].astype(str) for c in group]
    df["label"] = pd.concat(parts, axis=1).agg(" / ".join, axis=1)

    totals = {name: len(Grid.load(Path(__file__).parent / name).treasures) for name in df["grid"].unique()}
    df["solved"] = df["treasures"] >= df["grid"].map(totals)

    runs = df.groupby("run").agg(
        label=("label", "first"),
        generations=("generation", "max"),
        moves=("moves", "last"),
        elapsed=("elapsed", "last"),
    )
    runs["solved_at"] = df[df["solved"]].groupby("run")["generation"].min()
    runs["solution_moves"] = runs["moves"].where(runs["solved_at"].notna())

    return df, runs

def plot_fitness(df: pd.DataFrame, runs: pd.DataFrame, out: Path):

    best = df.pivot(index="generation", columns="run", values="best_so_far").ffill()
    avg = df.pivot(index="generation", columns="run", values="avg_fitness").ffill()

    fig, ax = plt.subplots(figsize=(10, 5))
    for i, (label, ids) in enumerate(runs.groupby("label").groups.items()):
        color = f"C{i}"
        best[ids].mean(axis=1).plot(ax=ax, color=color, label=f"{label} – best so far")
        avg[ids].mean(axis=1).plot(ax=ax, color=color, linestyle="--", label=f"{label} – population average")

    ax.set(title="Fitness over generations (mean over runs)", xlabel="generation", ylabel="fitness")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "fitness.png", dpi=150)

def plot_success(runs: pd.DataFrame, out: Path):
    generations = range(1, int(runs["generations"].max()) + 1)

    fig, ax = plt.subplots(figsize=(10, 5))
    for label, group in runs.groupby("label"):
        solved = group["solved_at"].value_counts().reindex(generations, fill_value=0).cumsum()
        (100 * solved / len(group)).plot(ax=ax, drawstyle="steps-post", label=label)

    ax.set(title="Runs that found all treasures", xlabel="generation", ylabel="runs solved (%)", ylim=(0, 105))
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "success.png", dpi=150)

def plot_results(runs: pd.DataFrame, out: Path):
    solved = runs.dropna(subset=["solved_at"])

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for ax, column in zip(axes, ["solved_at", "solution_moves"]):
        solved.boxplot(column=column, by="label", ax=ax, showfliers=False)
        for i, (_, group) in enumerate(solved.groupby("label"), 1):
            ax.scatter([i] * len(group), group[column], color="C0", alpha=0.6, zorder=3)
            
    axes[0].set(title="Generations to find all treasures", xlabel="", ylabel="generation")
    axes[1].set(title="Path length of the solution", xlabel="", ylabel="moves")
    for ax in axes:
        ax.set_xticks(ax.get_xticks(), [t.get_text().replace(" / ", "\n") for t in ax.get_xticklabels()])
    fig.suptitle("")
    fig.tight_layout()
    fig.savefig(out / "results.png", dpi=150)

def summary(runs: pd.DataFrame) -> pd.DataFrame:
    table = runs.groupby("label").agg(
        runs=("solved_at", "size"),
        solved=("solved_at", "count"),
        gens_median=("solved_at", "median"),
        gens_mean=("solved_at", "mean"),
        moves_median=("solution_moves", "median"),
        time_mean=("elapsed", "mean"),
    )
    table.insert(2, "solved_%", 100 * table["solved"] / table["runs"])
    return table.round(1)

def main():
    parser = argparse.ArgumentParser(description="Plot runs logged with `project2.py --export FILE`.")
    parser.add_argument("csv", type=Path, help="CSV written by project2.py --export")
    parser.add_argument("--group", nargs="+", default=["selection"], help="setting column(s) to compare by")
    parser.add_argument("--out", type=Path, default=Path("plots"), help="output directory")
    parser.add_argument("--show", action="store_true", help="also open the plots in a window")
    args = parser.parse_args()

    df, runs = load(args.csv, args.group)
    args.out.mkdir(parents=True, exist_ok=True)

    plot_fitness(df, runs, args.out)
    plot_success(runs, args.out)
    plot_results(runs, args.out)

    table = summary(runs)
    print(table.to_string())
    print(f"\nPlots written to {args.out}/")

    few = table[table["runs"] < 5]
    if not few.empty:
        print(
            f"\nNote: {', '.join(few.index)} has fewer than 5 runs. success.png and results.png compare many runs, "
            "so run project2.py with several --seed values (same --export file) to fill them."
        )

    if args.show:
        plt.show()

if __name__ == "__main__":
    main()
