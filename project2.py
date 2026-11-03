from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import asdict, dataclass
import argparse
import csv
from functools import partial
import random
import sys
import time
from pathlib import Path
from typing import Callable

type Individual = bytes

RESET, BOLD, DIM, RED, GREEN, YELLOW, CYAN = "\033[0m", "\033[1m", "\033[2m", "\033[31m", "\033[32m", "\033[33m", "\033[36m"
DIRECTIONS = ["H", "D", "P", "L"]
MOVES = {"H": (-1, 0), "D": (1, 0), "P": (0, 1), "L": (0, -1)}
ARROWS = {"H": "↑", "D": "↓", "P": "→", "L": "←"}

DEFAULT_TREASURES = {(1, 4), (2, 2), (3, 6), (4, 1), (5, 4)}
DEFAULT_GRID = Path(__file__).parent / "grid.txt"
MEMORY_CELLS = 64

DEFAULT_EXPORT = Path(__file__).parent / "runs.csv"

class Grid():

    def __init__(
        self,
        width: int = 7,
        height: int = 7,
        start: tuple[int, int] = (6, 3),
        treasures: set[tuple[int, int]] = DEFAULT_TREASURES,
    ):
        if width <= 0 or height <= 0:
            raise ValueError("Grid dimensions must be positive.")

        self.width = width
        self.height = height
        self.start = start
        self.treasures = frozenset(treasures)
        self.exits: dict[tuple[int, int], str] = {}

        if not self.in_bounds(start):
            raise ValueError("Start is outside the grid.")
        for t in self.treasures:
            if not self.in_bounds(t):
                raise ValueError(f"Treasure {t} is outside the grid.")

        self.reset()

    def reset(self):
        self.position = self.start
        self.found: set[tuple[int, int]] = set(self.treasures & {self.start})
        self.moves = 0
        self.out_of_bounds = False
        self.exits = {}

    def in_bounds(self, pos: tuple[int, int]) -> bool:
        r, c = pos
        return 0 <= r < self.height and 0 <= c < self.width

    def move(self, direction: str):

        dr, dc = MOVES[direction]
        new_pos = (self.position[0] + dr, self.position[1] + dc)
        self.moves += 1
        self.exits[self.position] = direction

        if not self.in_bounds(new_pos):
            self.out_of_bounds = True
            return

        self.position = new_pos
        if new_pos in self.treasures:
            self.found.add(new_pos)

    @property
    def all_found(self) -> bool:
        return len(self.found) == len(self.treasures)

    @property
    def finished(self) -> bool:
        return self.out_of_bounds or self.all_found

    def fitness(self) -> float:
        return len(self.found) + 1 - 0.001 * self.moves

    def render(self, color: bool = False) -> str:

        def paint(text: str, style: str) -> str:
            return f"{style}{text}{RESET}" if color else text

        rows = []
        for r in range(self.height):
            row = []
            for c in range(self.width):
                p = (r, c)
                if p == self.position and not self.out_of_bounds:
                    ch = paint("@", BOLD + YELLOW)
                elif p in self.found:
                    ch = paint("$", BOLD + GREEN)
                elif p in self.treasures:
                    ch = paint("T", RED)
                elif p == self.start:
                    ch = paint("S", BOLD)
                elif p in self.exits:
                    ch = paint(ARROWS[self.exits[p]], CYAN)
                else:
                    ch = paint(".", DIM)
                row.append(ch)
            rows.append(" ".join(row))
        return "\n".join(rows)

    def __str__(self) -> str:
        return self.render()

    @classmethod
    def load(cls, path: Path) -> "Grid":

        with path.open("r", encoding="utf-8") as file:
            lines = file.read().splitlines()

        while lines and not lines[-1].strip():
            lines.pop()

        height = len(lines)
        width = max((len(line) for line in lines), default=0)
        start = None
        treasures = []

        for r, line in enumerate(lines):
            for c, char in enumerate(line):
                if char == 'S':
                    if start is not None:
                        raise ValueError(f"Multiple start positions: {start} and {(r, c)}.")
                    start = (r, c)
                elif char == 'T':
                    treasures.append((r, c))

        if width == 0 or height == 0:
            raise ValueError("File is empty.")

        if start is None:
            raise ValueError("Start position is not found.")

        if not treasures:
            raise ValueError("Grid does not contain treasure.")

        return cls(width=width, height=height, start=start, treasures=treasures)


class Memory():

    def __init__(self, *, data: Sequence[int]):
        self.load(data)

    @property
    def size(self):
        return len(self._data)

    def validate_bounds(self, address: int):
        if address < 0 or address >= self.size:
            raise ValueError(f"Address is out of bounds. Allowed addresses: [0, {self.size - 1}]")
    
    def get(self, address: int) -> int:
        self.validate_bounds(address)
        return self._data[address]

    def set(self, address: int, value: int):
        self.validate_bounds(address)
        value = value & 0xFF
        self._data[address] = value

    def load(self, data: Sequence[int]):

        size = len(data)

        if size <= 1:
            raise ValueError(f"Memory must have >1 cells.")

        self._data = [value & 0xFF for value in data]

    def __len__(self):
        return len(self._data)


@dataclass(frozen=True)
class InstructionMeta():
    code: int
    name: str

INCREMENT_META = InstructionMeta(0, "INC") 
DECREMENT_META = InstructionMeta(1, "DEC") 
JUMP_META = InstructionMeta(2, "JMP") 
WRITE_META = InstructionMeta(3, "WRT")


class Instruction(ABC):

    def __init__(self, meta: InstructionMeta, arg: int):

        if arg < 0 or arg > 63:
            raise ValueError("Argument out of range. Range [0, 63] (6 bits).")

        super().__init__()
        self._meta = meta
        self.arg = arg

    @abstractmethod
    def apply(self, vm: "VirtualMachine"):
        ...

    def __repr__(self):
        return f"{self._meta.name}, {self.arg}"

class Increment(Instruction):

    def __init__(self, arg: int):
        super().__init__(INCREMENT_META, arg)

    def apply(self, vm: "VirtualMachine"):
        vm.memory.set(self.arg, vm.memory.get(self.arg) + 1)
        vm.advance()

class Decrement(Instruction):

    def __init__(self, arg: int):
        super().__init__(DECREMENT_META, arg)

    def apply(self, vm: "VirtualMachine"):
        vm.memory.set(self.arg, vm.memory.get(self.arg) - 1)
        vm.advance()

class Jump(Instruction):

    def __init__(self, arg: int):
        super().__init__(JUMP_META, arg)

    def apply(self, vm: "VirtualMachine"):
        vm.ip = self.arg

class Write(Instruction):

    def __init__(self, arg: int):
        super().__init__(WRITE_META, arg)

    def apply(self, vm: "VirtualMachine"):
        value = vm.memory.get(self.arg)
        vm.output.append(DIRECTIONS[value & 0b11])
        vm.advance()

INSTRUCTION_REGISTRY = {
    INCREMENT_META.code: Increment,
    DECREMENT_META.code: Decrement,
    JUMP_META.code: Jump,
    WRITE_META.code: Write,
}


def decode(n: int) -> Instruction:
    code, arg = n >> 6, n & 0b111111
    cls = INSTRUCTION_REGISTRY.get(code, None)
    if cls is None:
        raise ValueError(f"Instruction with code '{code}' does not exist.")
    return cls(arg)


def as_binary_str(n: int, bits: int = 8) -> str:
    return "".join(str((n >> i) & 1) for i in range(bits - 1, -1, -1))


class VirtualMachine():

    def __init__(self, memory: Memory, *, max_steps: int = 500, wrap: bool = False):

        if not memory:
            raise ValueError("Memory cannot be None.")

        self.memory = memory
        self.max_steps = max_steps
        self.wrap = wrap

        self.steps = 0
        self.ip = 0
        self._halted = False

        self.output: list[str] = []

    @property
    def halted(self) -> bool:
        return self._halted

    def halt(self):
        self._halted = True

    def advance(self):
        self.ip += 1
        if self.ip >= len(self.memory):
            if self.wrap:
                self.ip = 0
            else:
                self.halt()

    def fetch(self) -> int:
        return self.memory.get(self.ip)

    def step(self):
        if self._halted:
            return
        encoded = self.fetch()
        instruction = decode(encoded)
        instruction.apply(self)

        self.steps += 1
        if self.steps >= self.max_steps:
            self.halt()

    def reset(self, data: Sequence[int]):
        self.memory.load(data)
        self.ip = 0
        self.steps = 0
        self._halted = False
        self.output.clear() 


def evaluate(individual: Individual, vm: VirtualMachine, grid: Grid) -> float:

    vm.reset(individual)
    grid.reset()

    while not vm.halted and not grid.finished:
        before = len(vm.output)
        vm.step()
        if len(vm.output) > before:
            grid.move(vm.output[-1])

    if grid.moves == 0 and not grid.found:
        return 1 - 0.001 * vm.max_steps

    return grid.fitness()


def generate_population(cells: int = 64, n: int = 20, init_cells: int | None = None) -> list[Individual]:
    if init_cells is None:
        init_cells = cells
    return [bytes(random.randint(0, 255) if i < init_cells else 0 for i in range(cells)) for _ in range(n)]


def select_roulette(population: list[Individual], fits: list[float]) -> tuple[Individual, Individual]:
    father, mother = random.choices(population, weights=fits, k=2)
    return father, mother


def select_tournament(population: list[Individual], fits: list[float], size: int = 3) -> tuple[Individual, Individual]:
    def pick():
        idx = random.sample(range(len(population)), size)
        return population[max(idx, key=lambda i: fits[i])]
    return pick(), pick()


SELECTIONS: dict[str, Callable[[list[Individual], list[float]], tuple[Individual, Individual]]] = {
    "ROULETTE": select_roulette,
    "TOURNAMENT": select_tournament
}


def crossover_one_point(father: Individual, mother: Individual) -> tuple[Individual, Individual]:
    length = min(len(father), len(mother))
    cut = random.randint(1, length - 1)
    return father[:cut] + mother[cut:], mother[:cut] + father[cut:]


def crossover_two_point(father: Individual, mother: Individual) -> tuple[Individual, Individual]:
    length = min(len(father), len(mother))
    a, b = sorted(random.sample(range(1, length), 2))
    return father[:a] + mother[a:b] + father[b:], mother[:a] + father[a:b] + mother[b:]


CROSSOVERS: dict[str, Callable[[Individual, Individual], tuple[Individual, Individual]]] = {
    "ONE_POINT": crossover_one_point,
    "TWO_POINT": crossover_two_point,
}


@dataclass(frozen=True)
class MutationRates():
    bit_flip: float = 0.02
    random_cell: float = 0.01
    invert: float = 0.005

    swap: float = 0.05
    insert: float = 0.05
    delete: float = 0.05


def mutate(individual: Individual, rates: MutationRates = MutationRates()) -> Individual:
    individual = bytearray(individual)
    size = len(individual)

    for i in range(size):
        if random.random() < rates.bit_flip:
            individual[i] ^= 1 << random.randint(0, 7)
        if random.random() < rates.random_cell:
            individual[i] = random.randint(0, 255)
        if random.random() < rates.invert:
            individual[i] ^= 0xFF

    if random.random() < rates.swap:
        i = random.randrange(size - 1)
        individual[i], individual[i + 1] = individual[i + 1], individual[i]

    if random.random() < rates.insert:
        individual.insert(random.randrange(size), random.randint(0, 255))
        individual.pop()

    if random.random() < rates.delete:
        individual.pop(random.randrange(size))
        individual.append(0)

    return bytes(individual)


def print_solution(individual: Individual, vm: VirtualMachine, grid: Grid, delay: float = 0.15):

    fitness = evaluate(individual, vm, grid)

    print(f"Treasures: {len(grid.found)}/{len(grid.treasures)}, moves: {grid.moves}, fitness: {fitness:.3f}")
    print("Program:")
    for address, value in enumerate(individual):
        print(f"  {address:02d}: {as_binary_str(value)}  {decode(value)}")
    print("Path:", " ".join(vm.output))
    animate(grid, vm.output.copy(), delay)


def animate(grid: Grid, path: list[str], delay: float = 0.15):

    color = sys.stdout.isatty()
    grid.reset()

    def frame(step: int) -> str:
        status = f"Step {step}/{len(path)}"
        if step:
            status += f": {path[step - 1]}"
        status += f"  treasures {len(grid.found)}/{len(grid.treasures)}"
        if grid.out_of_bounds:
            status += "  (left the grid)"
        return grid.render(color) + "\n" + status

    if not color:
        for direction in path:
            grid.move(direction)
        print(frame(len(path)))
        return

    print(frame(0))
    for step, direction in enumerate(path, 1):
        time.sleep(delay)
        grid.move(direction)
        print(f"\033[{grid.height + 1}F", end="")
        print(frame(step) + "\033[K")

    print(f"Legend: S start  @ walker  {ARROWS['P']} path  T treasure  $ found")


GENERATION_FIELDS = [
    "generation",
    "best_fitness",
    "avg_fitness",
    "worst_fitness",
    "best_so_far",
    "treasures",
    "moves",
    "unique",
    "elapsed", 
]


class GenerationLog():

    def __init__(self, path: Path | None, settings: dict[str, object]):
        self.settings = settings
        self._file = None
        if path is None:
            return

        new = not path.exists() or path.stat().st_size == 0
        self._file = path.open("a", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=[*settings, *GENERATION_FIELDS])
        if new:
            self._writer.writeheader()

    def write(self, **stats: object):
        if self._file is not None:
            self._writer.writerow({**self.settings, **stats})

    def __enter__(self) -> "GenerationLog":
        return self

    def __exit__(self, *exc):
        if self._file is not None:
            self._file.close()


def main(
    pop_size: int = 30, 
    generations: int = 200, 
    elite: int = 2, 
    mutation: MutationRates = MutationRates(), 
    selector: str = "ROULETTE",
    crossover: str = "ONE_POINT",
    seed: int | None = None,
    find_best: bool = False,
    grid_path: Path = DEFAULT_GRID,
    tournament_size: int = 3,
    init_cells: int = MEMORY_CELLS,
    wrap: bool = False,
    delay: float = 0.15,
    log_path: Path | None = None,
):

    if pop_size < 20:
        raise ValueError("Population must have at least 20 individuals.")
    if not 0 <= elite < pop_size:
        raise ValueError(f"Elite must be in [0, {pop_size - 1}].")
    if not 2 <= tournament_size <= pop_size:
        raise ValueError(f"Tournament size must be in [2, {pop_size}].")
    if not 1 <= init_cells <= MEMORY_CELLS:
        raise ValueError(f"Initialized cells must be in [1, {MEMORY_CELLS}].")

    if selector not in SELECTIONS:
        raise ValueError(f"Unknown selection '{selector}'. Choose from: {', '.join(SELECTIONS)}.")
    select = SELECTIONS[selector]
    if select is select_tournament:
        select = partial(select_tournament, size=tournament_size)

    if crossover not in CROSSOVERS:
        raise ValueError(f"Unknown crossover '{crossover}'. Choose from: {', '.join(CROSSOVERS)}.")
    cross = CROSSOVERS[crossover]

    if seed is None:
        seed = random.randrange(2**32)
    random.seed(seed)

    grid = Grid.load(grid_path)
    vm = VirtualMachine(memory=Memory(data=[0] * MEMORY_CELLS), wrap=wrap)

    selection_name = f"{selector} (size {tournament_size})" if selector == "TOURNAMENT" else selector
    print(f"Seed: {seed}")
    print(f"Grid: {grid_path} ({grid.width}x{grid.height}, {len(grid.treasures)} treasures)")
    print(f"Population: {pop_size}, generations: {generations}, elite: {elite}, initialized cells: {init_cells}")
    print(f"Selection: {selection_name}, crossover: {crossover}, end of memory: {'wrap' if wrap else 'halt'}")
    print(f"Mutation: {mutation}\n")

    settings = {
        "grid": grid_path.name,
        "seed": seed,
        "pop_size": pop_size,
        "elite": elite,
        "selection": selector,
        "tournament_size": tournament_size if selector == "TOURNAMENT" else "",
        "crossover": crossover,
        "init_cells": init_cells,
        "wrap": wrap,
        **asdict(mutation),
    }

    population = generate_population(MEMORY_CELLS, pop_size, init_cells)
    best: Individual = population[0]
    best_fit = float("-inf")
    gen = 0
    started = time.perf_counter()

    with GenerationLog(log_path, settings) as log:
        while True:
            for _ in range(generations):
                gen += 1

                fits = [evaluate(individual, vm, grid) for individual in population]
                ranked = sorted(range(pop_size), key=lambda i: fits[i], reverse=True)

                evaluate(population[ranked[0]], vm, grid)

                if fits[ranked[0]] > best_fit:
                    best, best_fit = population[ranked[0]], fits[ranked[0]]
                    print(f"Gen {gen}: best fitness {best_fit:.3f} ({len(grid.found)}/{len(grid.treasures)} treasures, {grid.moves} moves)")

                log.write(
                    generation=gen,
                    best_fitness=round(fits[ranked[0]], 4),
                    avg_fitness=round(sum(fits) / pop_size, 4),
                    worst_fitness=round(fits[ranked[-1]], 4),
                    best_so_far=round(best_fit, 4),
                    treasures=len(grid.found),
                    moves=grid.moves,
                    unique=len(set(population)),
                    elapsed=round(time.perf_counter() - started, 3),
                )

                if grid.all_found and not find_best:
                    print(f"\nAll treasures found in generation {gen}:")
                    print_solution(best, vm, grid, delay)
                    return

                new_population = [population[i] for i in ranked[:elite]]

                while len(new_population) < pop_size:
                    father, mother = select(population, fits)
                    child1, child2 = cross(father, mother)
                    new_population += [mutate(child1, mutation), mutate(child2, mutation)]

                population = new_population[:pop_size]

            print(f"\nBest solution after {gen} generations:")
            print_solution(best, vm, grid, delay)

            try:
                answer = input(f"\nRun another {generations} generations? [y/N] ")
            except EOFError:
                answer = ""
            if answer.strip().lower() != "y":
                return


def probability(text: str) -> float:
    value = float(text)
    if not 0 <= value <= 1:
        raise argparse.ArgumentTypeError(f"{value} is not a probability in [0, 1].")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Treasure hunt solved by evolutionary programming over a 64-cell virtual machine.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    run = parser.add_argument_group("run")
    run.add_argument("--grid", type=Path, default=DEFAULT_GRID, help="grid file (S = start, T = treasure)")
    run.add_argument("--seed", type=int, default=None, help="random seed (random if omitted)")
    run.add_argument("--find-best", action="store_true", help="don't stop at the first solution, keep searching for a shorter path")
    run.add_argument("--delay", type=float, default=0.15, help="seconds between animation frames")

    evolution = parser.add_argument_group("evolution")
    evolution.add_argument("--pop-size", type=int, default=200, help="individuals per generation (at least 20)")
    evolution.add_argument("--generations", type=int, default=500, help="generations before asking to continue")
    evolution.add_argument("--elite", type=int, default=2, help="best individuals copied unchanged (0 = no elitism)")
    evolution.add_argument("--selection", type=str.upper, choices=SELECTIONS, default="ROULETTE")
    evolution.add_argument("--tournament-size", type=int, default=3, help="individuals per tournament")
    evolution.add_argument("--crossover", type=str.upper, choices=CROSSOVERS, default="ONE_POINT")
    evolution.add_argument("--init-cells", type=int, default=MEMORY_CELLS, help="leading cells randomized in the first generation, the rest are zero")
    evolution.add_argument("--wrap", action="store_true", help="continue from address 0 after the last cell instead of halting")

    rates = MutationRates()
    mutation = parser.add_argument_group("mutation probabilities")
    mutation.add_argument("--bit-flip", type=probability, default=rates.bit_flip, help="per cell: flip one random bit")
    mutation.add_argument("--random-cell", type=probability, default=rates.random_cell, help="per cell: replace with a random byte")
    mutation.add_argument("--invert", type=probability, default=rates.invert, help="per cell: invert all bits")
    mutation.add_argument("--swap", type=probability, default=rates.swap, help="per individual: swap two neighbouring cells")
    mutation.add_argument("--insert", type=probability, default=rates.insert, help="per individual: insert a random cell, drop the last")
    mutation.add_argument("--delete", type=probability, default=rates.delete, help="per individual: delete a cell, append zero")

    logs = parser.add_argument_group("logs")
    logs.add_argument("--export", type=Path, default=DEFAULT_EXPORT, help="log output file")

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        main(
            pop_size=args.pop_size,
            generations=args.generations,
            elite=args.elite,
            mutation=MutationRates(
                bit_flip=args.bit_flip,
                random_cell=args.random_cell,
                invert=args.invert,
                swap=args.swap,
                insert=args.insert,
                delete=args.delete,
            ),
            selector=args.selection,
            crossover=args.crossover,
            seed=args.seed,
            find_best=args.find_best,
            grid_path=args.grid,
            tournament_size=args.tournament_size,
            init_cells=args.init_cells,
            wrap=args.wrap,
            delay=args.delay,
            log_path=args.export,
        )
    except (ValueError, OSError) as e:
        sys.exit(f"Error: {e}")