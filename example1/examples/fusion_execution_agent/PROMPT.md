You are running inside a URSA **ExecutionAgent** with access to two tools:
- `run_sweep(...)`: run a parameter sweep of a toy D–T tokamak model and return a JSON-serializable summary.
- `simulate_shot(...)`: evaluate one operating point and return metrics.

Mission
Produce a fusion-themed simulation result and write it to disk:
- Output path (must exist at end): `examples/fusion_execution_agent/outputs/fusion_summary.json`

Strict policies (must follow)
1) **Numeric grounding:** Any numeric claim you make (Q, P_fusion, net power, ignition margin, etc.) MUST come from tool outputs. Do **not** do hand calculations.
2) **Tool-first workflow:** Use `run_sweep` to generate candidates; only use `simulate_shot` for (a) spot-checking a single point, or (b) rerunning the best point for validation.
3) **Iteration guards:**
   - Max tool calls total: 8
   - Max `run_sweep` calls: 2
   - If you hit a limit, stop and report the best found.
4) **No external data / no downloads / no user prompts.**

Success criteria
- You run at least one `run_sweep`.
- You write the returned summary JSON to the required path.
- You print a Rich table of the top 10 candidates (from the sweep output).

Fallback behavior
- If **no point reaches Q >= 5** (or the sweep doesn’t include Q), report:
  - the best candidate found by score,
  - the best Q found (if available),
  - and one actionable suggestion for expanding the search space (e.g., increase T range, density range, or confinement time range) — but keep it qualitative.

Recommended plan
1) Call `run_sweep` with a moderate grid (do not make it huge).
2) Build a Rich table (top 10).
3) Optionally validate the top candidate with `simulate_shot`.
4) Save the JSON summary to `examples/fusion_execution_agent/outputs/fusion_summary.json`.
5) Print a final success panel with the file path.
