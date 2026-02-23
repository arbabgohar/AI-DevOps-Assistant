"""
ClawOps CLI – Typer-based command-line interface.

The CLI reuses all existing core logic (plugins, action_router, log_agent)
directly – no HTTP server is required.  This means it works in CI pipelines,
cron jobs, and developer terminals without spinning up uvicorn.

Entry point
-----------
    python cli.py <command> [options]

Or, after ``pip install -e .``:
    clawops <command> [options]

Commands
--------
    clawops k8s analyze   [--namespace TEXT]
    clawops k8s logs      <pod> [--namespace TEXT] [--tail INT] [--analyze]
    clawops k8s pods      [--namespace TEXT]
    clawops k8s restart   <pod> [--namespace TEXT] [--yes]
    clawops docker analyze
    clawops docker ps
    clawops logs analyze  <log-file>  [--structured]
    clawops monitor

Security notes
--------------
- The ``--yes`` / ``approve`` flags are explicit operator gates.
- LLM output is always validated against schemas.LLMAnalysisResponse before
  reaching the action router.
- The CLI never constructs shell strings or calls subprocess from LLM output.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()
app = typer.Typer(
    name="clawops",
    help="[bold cyan]ClawOps[/] – AI DevOps Copilot CLI",
    rich_markup_mode="rich",
    no_args_is_help=True,
)

# Sub-applications
k8s_app = typer.Typer(help="Kubernetes operations", no_args_is_help=True)
docker_app = typer.Typer(help="Docker operations", no_args_is_help=True)
logs_app = typer.Typer(help="Log analysis operations", no_args_is_help=True)

app.add_typer(k8s_app, name="k8s")
app.add_typer(docker_app, name="docker")
app.add_typer(logs_app, name="logs")


# =========================================================================== #
# Kubernetes commands                                                          #
# =========================================================================== #


@k8s_app.command("pods")
def k8s_pods(
    namespace: str = typer.Option("default", "--namespace", "-n", help="Kubernetes namespace"),
) -> None:
    """List pods in a namespace with health status."""
    plugin = _get_k8s_plugin(namespace)
    if plugin is None:
        return

    with console.status(f"[cyan]Fetching pods in namespace '{namespace}'…"):
        pods = plugin.get_pods(namespace)

    if not pods:
        console.print(f"[yellow]No pods found in namespace '{namespace}'.")
        return

    table = Table(title=f"Pods – {namespace}", show_header=True, header_style="bold cyan")
    table.add_column("Name", style="white")
    table.add_column("Phase", justify="center")
    table.add_column("Ready", justify="center")
    table.add_column("Restarts", justify="right")
    table.add_column("Issues")

    for pod in pods:
        phase_color = {
            "Running": "green",
            "Pending": "yellow",
            "Failed": "red",
            "Succeeded": "blue",
        }.get(pod.get("phase", ""), "white")

        ready_icon = "[green]✓" if pod.get("ready") else "[red]✗"
        issues_text = ", ".join(pod.get("issues", [])) or "[dim]–"

        table.add_row(
            pod["name"],
            f"[{phase_color}]{pod.get('phase', '?')}",
            ready_icon,
            str(pod.get("restart_count", 0)),
            issues_text,
        )

    console.print(table)


@k8s_app.command("analyze")
def k8s_analyze(
    namespace: str = typer.Option("default", "--namespace", "-n", help="Kubernetes namespace"),
    output_json: bool = typer.Option(False, "--json", help="Output raw JSON"),
) -> None:
    """Analyze all pods in a namespace and surface health issues."""
    plugin = _get_k8s_plugin(namespace)
    if plugin is None:
        return

    with console.status(f"[cyan]Analysing pods in namespace '{namespace}'…"):
        result = plugin.analyze()

    if output_json:
        rprint(json.dumps(result, indent=2))
        return

    total = result.get("total_pods", 0)
    unhealthy = result.get("unhealthy_pods", 0)
    status_line = (
        f"[green]{total} pod(s) checked – all healthy."
        if unhealthy == 0
        else f"[red]{unhealthy}/{total} pod(s) have issues."
    )
    console.print(Panel(status_line, title=f"Namespace: {namespace}", expand=False))

    for analysis in result.get("analyses", []):
        if not analysis.get("healthy"):
            _print_pod_analysis(analysis)


@k8s_app.command("logs")
def k8s_logs(
    pod: str = typer.Argument(..., help="Pod name"),
    namespace: str = typer.Option("default", "--namespace", "-n", help="Kubernetes namespace"),
    tail: int = typer.Option(100, "--tail", help="Number of log lines to fetch"),
    container: Optional[str] = typer.Option(None, "--container", "-c", help="Container name"),
    analyze: bool = typer.Option(False, "--analyze", help="Run AI analysis on the fetched logs"),
) -> None:
    """Fetch and optionally analyze logs from a pod."""
    plugin = _get_k8s_plugin(namespace)
    if plugin is None:
        return

    with console.status(f"[cyan]Fetching logs for pod '{pod}'…"):
        try:
            logs = plugin.get_pod_logs(pod=pod, namespace=namespace, tail_lines=tail, container=container)
        except Exception as exc:
            console.print(f"[red]Error fetching logs: {exc}")
            raise typer.Exit(1) from exc

    console.rule(f"[cyan]Logs – {namespace}/{pod}")
    console.print(logs or "[dim](no log output)")

    if analyze:
        console.rule("[cyan]AI Analysis")
        _run_log_analysis(logs)


@k8s_app.command("restart")
def k8s_restart(
    pod: str = typer.Argument(..., help="Pod name to restart"),
    namespace: str = typer.Option("default", "--namespace", "-n", help="Kubernetes namespace"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Restart a pod by deleting it (controller will recreate it).

    Requires explicit approval via --yes or interactive prompt.
    All restart actions are recorded in audit.log.
    """
    if not yes:
        confirmed = typer.confirm(
            f"Restart pod '{pod}' in namespace '{namespace}'? This will delete the pod."
        )
        if not confirmed:
            console.print("[yellow]Aborted.")
            raise typer.Exit()

    # Build a minimal LLMAnalysisResponse to pass through the action router
    # so all security gates apply even for direct CLI invocations.
    from schemas.llm_response import AllowedAction, LLMAnalysisResponse, SuggestedAction
    from action_router import route_action, ActionRouterError

    analysis = LLMAnalysisResponse(
        issue_summary=f"Operator-initiated restart of pod '{pod}'",
        probable_cause="Manual CLI invocation",
        suggested_action=SuggestedAction(
            action=AllowedAction.RESTART_POD,
            parameters={"pod": pod, "namespace": namespace},
        ),
    )

    plugin_kwargs = {"namespace": namespace}
    try:
        with console.status("[cyan]Executing restart via action router…"):
            result = route_action(analysis, approved=True, plugin_kwargs=plugin_kwargs)
    except ActionRouterError as exc:
        console.print(f"[red]Action router rejected the request: {exc}")
        raise typer.Exit(1) from exc

    icon = "[green]✓" if result["success"] else "[red]✗"
    console.print(f"{icon} {result['message']}")
    console.print("[dim](recorded in audit.log)")


# =========================================================================== #
# Docker commands                                                              #
# =========================================================================== #


@docker_app.command("ps")
def docker_ps() -> None:
    """List all Docker containers with status and health."""
    plugin = _get_docker_plugin()
    if plugin is None:
        return

    with console.status("[cyan]Listing containers…"):
        state = plugin.get_state()

    containers = state.get("containers", [])
    if not containers:
        console.print("[yellow]No containers found.")
        return

    table = Table(title="Docker Containers", show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="white")
    table.add_column("Image")
    table.add_column("Status", justify="center")
    table.add_column("Health", justify="center")

    for c in containers:
        status_color = "green" if c["status"] == "running" else "red"
        health = c.get("health") or "–"
        health_color = {"healthy": "green", "unhealthy": "red", "starting": "yellow"}.get(
            health, "dim"
        )
        table.add_row(
            c["id"],
            c["name"],
            c["image"],
            f"[{status_color}]{c['status']}",
            f"[{health_color}]{health}",
        )

    console.print(table)


@docker_app.command("analyze")
def docker_analyze(
    output_json: bool = typer.Option(False, "--json", help="Output raw JSON"),
) -> None:
    """Analyze Docker containers for health issues."""
    plugin = _get_docker_plugin()
    if plugin is None:
        return

    with console.status("[cyan]Analysing Docker containers…"):
        result = plugin.analyze()

    if output_json:
        rprint(json.dumps(result, indent=2))
        return

    unhealthy = result.get("unhealthy_count", 0)
    total = result.get("total_containers", 0)
    status_line = (
        f"[green]{total} container(s) checked – all healthy."
        if unhealthy == 0
        else f"[red]{unhealthy}/{total} container(s) have issues."
    )
    console.print(Panel(status_line, title="Docker Analysis", expand=False))

    for issue in result.get("issues", []):
        console.print(f"  [red]• {issue}")

    console.rule("[cyan]Recommendations")
    for rec in result.get("recommendations", []):
        console.print(f"  [cyan]→ {rec}")


# =========================================================================== #
# Log analysis commands                                                        #
# =========================================================================== #


@logs_app.command("analyze")
def logs_analyze(
    log_file: Path = typer.Argument(..., help="Path to log file", exists=True, readable=True),
    structured: bool = typer.Option(
        False,
        "--structured",
        help="Return structured JSON (LLMAnalysisResponse) instead of free-form text",
    ),
    execute: bool = typer.Option(
        False,
        "--execute",
        help="If structured analysis recommends an action, route it through the action router",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Auto-approve suggested actions (use carefully)"),
    output_json: bool = typer.Option(False, "--json", help="Output raw JSON result"),
) -> None:
    """Analyze a log file using the AI agent.

    With --structured the LLM is asked to return a validated JSON schema.
    With --structured --execute the suggested action is routed through
    the guarded action router (requires --yes or interactive confirmation).
    """
    log_text = log_file.read_text(encoding="utf-8", errors="ignore")

    if not log_text.strip():
        console.print("[yellow]Log file is empty.")
        raise typer.Exit()

    if structured:
        from log_agent import analyze_log_structured

        with console.status("[cyan]Running structured AI analysis…"):
            result = analyze_log_structured(log_text)

        if result is None:
            console.print(
                "[red]LLM returned output that failed schema validation. "
                "No action will be taken."
            )
            raise typer.Exit(1)

        if output_json:
            rprint(json.dumps(result.model_dump(), indent=2))
        else:
            _print_structured_analysis(result)

        if execute:
            _execute_structured_analysis(result, yes=yes)
    else:
        from log_agent import analyze_log

        with console.status("[cyan]Running AI analysis…"):
            recommendation = analyze_log(log_text)

        if output_json:
            rprint(json.dumps({"recommendation": recommendation}))
        else:
            console.rule("[cyan]AI Recommendation")
            console.print(recommendation)


# =========================================================================== #
# System monitor command                                                       #
# =========================================================================== #


@app.command("monitor")
def monitor() -> None:
    """Display live system metrics (CPU, memory, disk)."""
    from monitor import get_system_metrics

    with console.status("[cyan]Reading system metrics…"):
        metrics = get_system_metrics()

    cpu = metrics["cpu"]["usage_percent"]
    mem = metrics["memory"]
    disk = metrics["disk"]

    def _bar(pct: float) -> str:
        filled = int(pct / 10)
        color = "green" if pct < 70 else ("yellow" if pct < 90 else "red")
        return f"[{color}]{'█' * filled}{'░' * (10 - filled)}[/] {pct:.1f}%"

    console.print(Panel(
        f"[bold]CPU[/]     {_bar(cpu)}\n"
        f"[bold]Memory[/]  {_bar(mem['percent'])}  "
        f"({_bytes(mem['total'] - mem['available'])} / {_bytes(mem['total'])})\n"
        f"[bold]Disk[/]    {_bar(disk['percent'])}  "
        f"({_bytes(disk['used'])} / {_bytes(disk['total'])})",
        title="System Health",
        expand=False,
    ))


# =========================================================================== #
# Internal helpers                                                             #
# =========================================================================== #


def _get_k8s_plugin(namespace: str) -> "KubernetesPlugin | None":  # type: ignore[name-defined]
    """Instantiate the Kubernetes plugin or print an error and return None."""
    try:
        from plugins import registry
        return registry.get("kubernetes", namespace=namespace)
    except Exception as exc:
        console.print(f"[red]Kubernetes plugin unavailable: {exc}")
        console.print("[dim]Ensure 'kubernetes' is installed and a kubeconfig is reachable.")
        return None


def _get_docker_plugin() -> "DockerPlugin | None":  # type: ignore[name-defined]
    """Instantiate the Docker plugin or print an error and return None."""
    try:
        from plugins import registry
        return registry.get("docker")
    except Exception as exc:
        console.print(f"[red]Docker plugin unavailable: {exc}")
        console.print("[dim]Ensure 'docker' is installed and the Docker daemon is running.")
        return None


def _run_log_analysis(log_text: str) -> None:
    """Run free-form AI analysis and print the result."""
    try:
        from log_agent import analyze_log
        recommendation = analyze_log(log_text)
        console.print(recommendation)
    except Exception as exc:
        console.print(f"[red]AI analysis failed: {exc}")


def _print_pod_analysis(analysis: dict) -> None:
    """Pretty-print a single pod analysis dict."""
    title = f"[red]Pod: {analysis['pod']} ({analysis['namespace']})"
    lines: list[str] = [
        f"Phase: [yellow]{analysis.get('phase', '?')}",
        f"Restarts: [yellow]{analysis.get('restart_count', 0)}",
    ]
    for issue in analysis.get("issues", []):
        lines.append(f"[red]• Issue: {issue}")
    for rec in analysis.get("recommendations", []):
        lines.append(f"[cyan]→ {rec}")
    console.print(Panel("\n".join(lines), title=title, expand=False))


def _print_structured_analysis(result: "LLMAnalysisResponse") -> None:  # type: ignore[name-defined]
    """Pretty-print a validated LLMAnalysisResponse."""
    console.print(Panel(
        f"[bold]Summary:[/]        {result.issue_summary}\n"
        f"[bold]Probable cause:[/] {result.probable_cause}\n"
        f"[bold]Action:[/]         [cyan]{result.suggested_action.action.value}[/]\n"
        f"[bold]Parameters:[/]     {result.suggested_action.parameters}",
        title="Structured AI Analysis",
        expand=False,
    ))


def _execute_structured_analysis(
    result: "LLMAnalysisResponse",  # type: ignore[name-defined]
    *,
    yes: bool,
) -> None:
    """Route a structured analysis through the action router."""
    from action_router import route_action, ActionRouterError, dry_run

    action_token = result.suggested_action.action.value

    if action_token == "no_action":
        console.print("[green]No action required.")
        return

    preview = dry_run(result)
    console.print(Panel(
        f"[bold]Action:[/]       {preview['action']}\n"
        f"[bold]Plugin:[/]       {preview['plugin']}\n"
        f"[bold]Parameters:[/]   {preview['parameters']}\n"
        f"[bold]In allowlist:[/] {'[green]Yes' if preview['in_allowlist'] else '[red]No'}",
        title="Dry Run Preview",
        expand=False,
    ))

    if not preview["would_execute"]:
        console.print("[red]Action would not execute (allowlist or plugin issue). Aborting.")
        return

    approved = yes or typer.confirm(
        f"Execute action '{action_token}'? This will be logged to audit.log."
    )
    if not approved:
        console.print("[yellow]Aborted.")
        return

    try:
        with console.status("[cyan]Routing action…"):
            exec_result = route_action(result, approved=True)
        icon = "[green]✓" if exec_result["success"] else "[red]✗"
        console.print(f"{icon} {exec_result['message']}")
        console.print("[dim]Action recorded in audit.log.")
    except ActionRouterError as exc:
        console.print(f"[red]Action router error: {exc}")


def _bytes(n: int) -> str:
    """Human-readable byte count."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n //= 1024
    return f"{n:.1f} PB"


# =========================================================================== #
# Entry point                                                                  #
# =========================================================================== #

if __name__ == "__main__":
    app()
