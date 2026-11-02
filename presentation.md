# Presentation Script

This program consists of 4 parts - 4 executable python programs:

- **project2.py** - main file, where the algorithm and implementation of the task are located.
- **compare.py** - programs that conducts several runs of the program with different settings and records outcomes of each of them. After that it takes a group of runs and compares their results against each other.
- **experiment.py** - runs the prgoram with the best settings found using comparison on new seeds to ensure that specified settings are really the best.
- **plot.py** - creates plots from the records.

Algorithm works is arranged in the following way:

1. Generate a population of individuals, where each individual is an independent program with genes that are represented as 64 byte-instructions. Population may be generated with 2 options: its size and initialised cells. Initialised cells are first N cells of the program which will randomly obtain instructions or values, the rest of 64 - N cells will be set to zero.

2. Initialise results with default values. Set best individual to the first program from the population and best fitness to negative infinity.

3. Calculate fitness of each individual.

4. Sort individuals by fitness.

5. Compare best general fitness with the best fitness from the current population. Set best total fitness to fitness of the program if its better.

6. Write log record.

7. If all treasures are found and `--find-best` flag is not set, stop the loop.

8. Initialise a new population with `--elite N` elements from previous one.

9. Start a nested loop that fills the new population until its size does not reach the max size of population:
    1. Take 2 parents from the old population using chosen selection strategy: Tournament or Roulette.
    2. Acquire 2 children by applying crossover function to the selected parents. Available crossover strategies: One point and Two point.
    3. Mutate children. There are 6 kinds of mutation, each has its probability and affects the program with distinct power.
    4. Add mutated children to the new population.

10. Set population to the new one.
11. Repeat steps 3 - 10 until all treasures are not found or program does not reach max amount of generations.