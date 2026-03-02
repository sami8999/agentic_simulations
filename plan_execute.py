import argparse
from pathlib import Path
from types import SimpleNamespace as NS

from dotenv import load_dotenv

load_dotenv()  

import yaml
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage

from ursa.agents import ExecutionAgent, PlanningAgent


def load_config(path: str) -> NS:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ValueError("Top-level YAML must be a mapping/object.")
    return NS(**raw)


def main(config_path: str, cli_model: str | None, workspace_override: str | None):
    cfg = load_config(config_path)

    problem = getattr(cfg, "problem", None)
    if not problem:
        raise ValueError("config.yaml must contain a top-level 'problem:' string")

    # --- MODEL RESOLUTION ---
    # Priority: CLI > YAML > fallback
    model_name = (
        cli_model
        or getattr(cfg, "model", None)
        or "openai:o4-mini"
    )

    print(f"\nUsing model: {model_name}")

    # --- WORKSPACE RESOLUTION ---
    workspace = (
        workspace_override
        or getattr(cfg, "workspace", None)
        or "mini_workspace"
    )
    Path(workspace).mkdir(parents=True, exist_ok=True)

    # Optional symlink dict that ExecutionAgent understands:
    symlinkdict = getattr(cfg, "symlink", None)

    # --- Build models ---
    planner_llm = init_chat_model(model=model_name)
    executor_llm = init_chat_model(model=model_name)

    # --- Build agents ---
    planner = PlanningAgent(
        llm=planner_llm,
        thread_id="demo_planner",
        workspace=workspace,
    )

    executor = ExecutionAgent(
        llm=executor_llm,
        thread_id="demo_executor",
        workspace=workspace,
    )

    # --- 1) PLAN ---
    planning_output = planner.invoke(problem)
    steps = planning_output["plan"].steps

    print("\n=== PLAN ===")
    for i, s in enumerate(steps, 1):
        name = getattr(s, "name", f"Step {i}")
        desc = getattr(s, "description", str(s))
        print(f"{i}. {name}\n   {desc}\n")

    # --- 2) EXECUTE ---
    last_summary = "No previous step."
    print("\n=== EXECUTION ===")

    for i, step in enumerate(steps, 1):
        step_text = (
            f"{getattr(step, 'name', f'Step {i}')}\n"
            f"{getattr(step, 'description', str(step))}"
        )

        prompt = (
            f"You are executing a multi-step plan.\n\n"
            f"Overall problem:\n{problem}\n\n"
            f"Previous-step summary:\n{last_summary}\n\n"
            f"Current step:\n{step_text}\n\n"
            f"Execute this step fully. Use tools if helpful. "
            f"If you write code, save it in the workspace.\n"
        )

        result = executor.invoke(
            {
                "messages": [HumanMessage(content=prompt)],
                "workspace": workspace,
                "symlinkdir": symlinkdict,
            }
        )

        last_summary = result["messages"][-1].text
        print(f"\n--- Step {i} result ---\n{last_summary}")

    print("\n=== FINAL ===")
    print(last_summary)
    print(f"\nWorkspace: {Path(workspace).resolve()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, help="Path to config.yaml")
    parser.add_argument(
        "--model",
        default=None,  # allow YAML to decide
        help="Model string for init_chat_model (e.g. openai:o4-mini)",
    )
    parser.add_argument(
        "--workspace",
        default=None,
        help="Override workspace directory (optional)",
    )
    args = parser.parse_args()

    main(args.config, args.model, args.workspace)