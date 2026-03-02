# Fusion ExecutionAgent example (URSA): toy tokamak performance scan

This example demonstrates how to use **URSA’s `ExecutionAgent`** to orchestrate a small, deterministic fusion-themed simulation via LangChain tools, with a **Rich** console report and **JSON outputs**.

It runs a parameter scan for a *toy* D–T tokamak steady-state model and computes (for each operating point):
- an approximate D–T reactivity vs ion temperature,
- fusion power density and alpha heating power density,
- toy bremsstrahlung radiation losses,
- toy transport losses (thermal energy / `τ_E`),
- net power density and an “ignition margin” score,
then ranks and reports the best candidates.

All physics is intentionally simplified—this is a **workflow + agent/tooling** example, not a validated reactor model.

## Directory layout
- `main.py` — entrypoint; runs either:
  - **online agent mode** (URSA `ExecutionAgent` + LLM) if `OPENAI_API_KEY` is set, or
  - **offline deterministic mode** (no LLM, no network) if `OPENAI_API_KEY` is missing.
- `offline_runner.py` — explicit offline entrypoint (always no-LLM).
- `fusion_simulation.py` — deterministic toy model + scan utilities.
- `fusion_tools.py` — LangChain tools wrapping the simulator (`simulate_shot`, `run_sweep`).
- `PROMPT.md` — agent task instructions (kept separate for easy iteration).
- `diagnostics.py` — optional environment/tool-call tracing (opt-in via env vars).
- `smoke_tests.py` — quick offline checks (no pytest needed).
- `outputs/` — generated JSON artifacts.

## Prerequisites
- Python 3.10+ (tested in the provided conda environment)
- URSA available in the current environment (already provided)
- No extra installs should be required.

## How to run
From the repository root:

### 1) Offline mode (recommended for quick deterministic runs)
Offline mode is automatically selected if `OPENAI_API_KEY` is not present.

```bash
env -u OPENAI_API_KEY python examples/fusion_execution_agent/main.py
```

Or run the dedicated offline entrypoint:

```bash
python examples/fusion_execution_agent/offline_runner.py
```

### 2) Online mode (URSA ExecutionAgent + LLM)
Ensure your shell has `OPENAI_API_KEY` set (the environment typically already does).

```bash
python examples/fusion_execution_agent/main.py
```

#### Model selection (online)
The script respects `URSA_MODEL` if set.

```bash
export URSA_MODEL="openai:gpt-5-mini"
python examples/fusion_execution_agent/main.py
```

If your URSA install supports other providers (Azure, etc.), use the corresponding `URSA_MODEL` string format required by your environment.

## Outputs (what to expect)
A successful run produces:
- `examples/fusion_execution_agent/outputs/fusion_summary.json` — summary including:
  - the best operating point found in the scan,
  - a short list of top candidates,
  - the scan grid and bookkeeping metadata.

Optional (only if enabled):
- `examples/fusion_execution_agent/outputs/tool_traces.json` — tool-call timing/arguments (see Diagnostics).
- `examples/fusion_execution_agent/outputs/smoke_tests_ok.json` — written by `smoke_tests.py` on success.

## Smoke tests (offline)
Runs a small suite of checks:
- import + single-point simulation,
- simple invariants (e.g., increased `τ_E` improves ignition margin),
- small sweep sanity + runtime guard.

```bash
env -u OPENAI_API_KEY python examples/fusion_execution_agent/smoke_tests.py
```

## Determinism and runtime
- The toy simulation is **deterministic** (no RNG). Offline runs should be bitwise stable on the same platform.
- Typical runtime is a few seconds; online mode may be longer depending on model latency.

## Diagnostics (opt-in)
These are **off by default** (so normal runs stay clean and fast).

### Environment diagnostics
Print extra environment details at startup:

```bash
FUSION_EXAMPLE_DEBUG=1 env -u OPENAI_API_KEY python examples/fusion_execution_agent/main.py
```

### Tool-call tracing
Record tool-call timings and arguments to `outputs/tool_traces.json`:

```bash
FUSION_EXAMPLE_TRACE_TOOLS=1 env -u OPENAI_API_KEY python examples/fusion_execution_agent/main.py
```

## Troubleshooting

### 1) Missing API key / no network access
If `OPENAI_API_KEY` is not set (or network calls fail), use offline mode:

```bash
env -u OPENAI_API_KEY python examples/fusion_execution_agent/main.py
```

### 2) Import errors for URSA
This repo treats `./ursa/` as read-only and relies on URSA being installed in the environment.
If you see `ModuleNotFoundError: ursa...`, you’re likely not in the provided conda env.

### 3) Schema / tool argument errors
The agent tools are strict about fields. If you edit `fusion_tools.py` or `fusion_simulation.py`, keep the sweep schema aligned with `ScanConfig` in `fusion_simulation.py`.

### 4) Rate limits / provider errors (online mode)
If the model provider rate-limits or errors, rerun in offline mode to verify the simulation still works, or set a smaller/cheaper model via `URSA_MODEL`.

### 5) Windows notes
Commands use `env -u` to unset variables (POSIX shells). On Windows PowerShell, use:

```powershell
Remove-Item Env:OPENAI_API_KEY
python examples/fusion_execution_agent/main.py
```
