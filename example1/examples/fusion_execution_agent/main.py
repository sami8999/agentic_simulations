from __future__ import annotations

import os
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from diagnostics import maybe_print_env_diagnostics

from langchain.chat_models import init_chat_model

from ursa.agents.execution_agent import ExecutionAgent

from fusion_tools import run_sweep, simulate_shot
from offline_runner import run_offline_demo


def main() -> None:
    console = Console()

    maybe_print_env_diagnostics()

    console.print(
        Panel.fit(
            "[bold cyan]URSA ExecutionAgent demo[/bold cyan]\n"
            "[white]Toy D–T Fusion Performance Explorer[/white]",
            border_style="cyan",
        )
    )

    # --- Offline fallback ---
    # If no API key is present, run a deterministic local sweep so the example is
    # still runnable. This avoids any network calls.
    if not os.environ.get("OPENAI_API_KEY"):
        example_dir = Path(__file__).resolve().parent
        run_offline_demo(example_dir)
        return

    # Model selection: prefer URSA_MODEL if present.
    model_name = os.environ.get("URSA_MODEL", "openai:gpt-5-mini")

    console.print(
        Panel.fit(
            f"[bold]Model:[/bold] [green]{model_name}[/green]\n"
            "[dim]Tip: set URSA_MODEL to override.[/dim]",
            title="Configuration",
            border_style="green",
        )
    )

    model = init_chat_model(model=model_name, temperature=0)

    # Put agent artifacts under this example directory.
    example_dir = Path(__file__).resolve().parent
    checkpoint_dir = example_dir / "checkpoints"
    outputs_dir = example_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    agent = ExecutionAgent(
        llm=model,
        # Control iteration via the prompt (tool-call caps, etc.).
        extra_tools=[simulate_shot, run_sweep],
        # Keep artifacts inside this example directory.
        workspace=str(example_dir),
    )

    prompt_path = example_dir / "PROMPT.md"
    prompt_text = prompt_path.read_text()

    # Give the agent a direct instruction to run the scan and write JSON.
    state = agent.invoke(prompt_text)

    console.print(Panel.fit("[bold green]Agent finished.[/bold green]", border_style="green"))

    # Print URSA's formatted result for debugging/visibility.
    console.print(agent.format_result(state))

    summary_path = outputs_dir / "fusion_summary.json"
    if summary_path.exists():
        console.print(
            Panel.fit(
                f"[bold green]Wrote:[/bold green] {summary_path}",
                title="Outputs",
                border_style="green",
            )
        )
    else:
        console.print(
            Panel.fit(
                "[bold red]Expected output JSON was not found.[/bold red]\n"
                f"Looked for: {summary_path}",
                title="Outputs",
                border_style="red",
            )
        )


if __name__ == "__main__":
    main()
