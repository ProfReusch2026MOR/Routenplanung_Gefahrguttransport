# Review Meeting Progress

## 1) Project Title
Hazardous Materials Vehicle Routing Optimization (HMVRP)

## 2) Team Members
- Luca Siewecke
- Timo Schöddert
- Maher Darweesh
- Jonas Beckmann
- Fuqiang Zhang

## 3) Core Decision Question
Which vehicles serve which hazardous-material deliveries on which permissible routes so that total risk is minimized and economic transport costs are kept within all logistics constraints?

## 4) Detailed Task Allocation
### Luca (Person A) - Project Coordination, GitHub Management
- Owns the repository structure including clear folder and file organization.
- Maintains and updates the README, project status, and meeting documentation.
- Manages GitHub issues and milestones (planning, prioritization, tracking).
- Conducts pull-request reviews and coordinates the integration of all sub-contributions.
- Handles integration management between data, model, solver, and heuristics.

### Timo (Person B) - Data Model and Data Generation
- Defines the data model for nodes, edges, deliveries, vehicles, and risk factors.
- Researches and structures suitable data sources and assumptions for instance parameters.
- Generates artificial instances in sizes small, medium, and large.
- Implements plausibility checks for value ranges, completeness, and consistency.
- Prepares reproducible input data for solver and heuristic tests.

### Maher (Person C) - Mathematical Model
- Defines sets, parameters, and decision variables formally and consistently.
- Formulates the objective function with risk as the primary objective and cost as the secondary objective.
- Models constraints (routing, capacities, time windows, flow/feasibility constraints).
- Documents model assumptions, system boundaries, and notation clearly in Markdown/notebook.
- Closely aligns the mathematical model with the data structure and solver mapping.

### Jonas (Person D) - Solver Implementation
- Implements the model in Python (e.g., Pyomo/Gurobi/OR-Tools/PuLP).
- Implements the exact MILP/LP approach according to the model description.
- Configures solver parameters, time limits, and analyzable run logs.
- Solves small instances as an initial validation of the model implementation.
- Documents runtime, gap, and solution quality for later comparative evaluation.

### Fuqiang (Person E) - Heuristics and Literature
- Conducts literature research on HMVRP risk models.
- Creates a structured literature summary with relevant methods and findings.
- Develops and implements initial heuristic methods (e.g., greedy, local search).
- Defines comparison ideas and evaluation logic for solver vs. heuristics.
- Supports the interpretation of experimental results in the research context.

## 5) Current Status of Core Components
*   **Data:** tbd

*   **Model:** tbd

*   **Solver:** tbd

*   **Heuristics:** tbd

*   **Experiments:** tbd

## 6) To-Dos
### Open Tasks
*   [ ] Initialize project structure on GitHub (GitHub issues, review meeting progress) - Luca
*   [ ] Find data sources - Timo, Jonas
*   [ ] Create an initial idea for a mathematical model - Maher
*   [ ] First implementation in PuLP - Jonas
*   [ ] Research literature - Fuqiang

### Completed Tasks
*   [x] tbd

## 7) Current Literature

*   *Source 1:* tbd

## 8) Known Problems, Risks & Questions for Feedback
*   **Known problems/risks:** tbd

*   **Questions for feedback:**
    1. tbd
