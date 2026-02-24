"""CVA Rich Terminal UI — Gemini CLI-style chatbot interface."""

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.text import Text
from rich.table import Table
from rich.rule import Rule
from rich.columns import Columns
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.brain.thinking import parse_thinking
from src.config import settings


console = Console()


def print_banner():
    """Display the CVA startup banner."""
    banner = Text()
    banner.append("╔══════════════════════════════════════════════════════════════╗\n", style="bold cyan")
    banner.append("║  ", style="bold cyan")
    banner.append("CVA", style="bold white")
    banner.append(" — Cognitive VAPT Assistant v2                       ", style="dim white")
    banner.append("║\n", style="bold cyan")
    banner.append("║  ", style="bold cyan")
    banner.append("AI-Powered Penetration Testing • ReAct Agent", style="dim white")
    banner.append("           ║\n", style="bold cyan")
    banner.append("║  ", style="bold cyan")
    banner.append("/help", style="bold yellow")
    banner.append(" for commands  •  ", style="dim white")
    banner.append("/target", style="bold yellow")
    banner.append(" to set target  •  ", style="dim white")
    banner.append("/exit", style="bold yellow")
    banner.append("     ║\n", style="bold cyan")
    banner.append("╚══════════════════════════════════════════════════════════════╝", style="bold cyan")
    console.print(banner)
    console.print()


def print_thinking(thinking_text: str):
    """Display thinking/reasoning trace in a collapsible-style panel."""
    # Truncate very long thinking blocks
    display_text = thinking_text[:800]
    if len(thinking_text) > 800:
        display_text += f"\n... ({len(thinking_text) - 800} chars omitted)"
    
    console.print(Panel(
        Text(display_text, style="dim italic"),
        title="[dim cyan]💭 Thinking[/dim cyan]",
        border_style="dim cyan",
        expand=False,
        padding=(0, 1),
    ))


def print_agent_response(content: str):
    """Display the agent's response with markdown rendering."""
    result = parse_thinking(content)
    
    # Only show thinking blocks in debug mode
    if result.thinking and settings.debug_mode:
        print_thinking(result.thinking)
    
    if result.content:
        console.print(Panel(
            Markdown(result.content),
            title="[bold green]🤖 CVA[/bold green]",
            border_style="green",
            padding=(1, 2),
        ))


def print_tool_call(tool_name: str, tool_args: dict):
    """Display a proposed tool call for user approval."""
    args_display = "\n".join(f"  {k}: {v}" for k, v in tool_args.items())
    
    console.print(Panel(
        f"[bold yellow]{tool_name}[/bold yellow]\n{args_display}",
        title="[bold yellow]⚡ Proposed Tool Call[/bold yellow]",
        border_style="yellow",
        padding=(0, 1),
    ))


def print_tool_result(tool_name: str, result: str):
    """Display tool execution result. Full output shown in debug mode."""
    if settings.debug_mode:
        console.print(Panel(
            Text(result[:5000] + (f"\n... ({len(result) - 5000} more chars)" if len(result) > 5000 else ""), style="dim"),
            title=f"[dim]📋 Raw Output: {tool_name}[/dim]",
            border_style="dim",
            padding=(0, 1),
        ))
    else:
        console.print(f"  [dim]✓ {tool_name} executed ({len(result)} chars)[/dim]")


def print_command_output(output: str):
    """Display slash command output."""
    console.print(Panel(
        Text(output),
        title="[bold blue]⚙ Command[/bold blue]",
        border_style="blue",
        padding=(0, 1),
    ))


def print_finding(title: str, severity: str, description: str = ""):
    """Display a discovered finding with severity coloring."""
    colors = {
        "critical": "bold red", "high": "bold bright_red",
        "medium": "bold yellow", "low": "bold blue", "info": "dim",
    }
    color = colors.get(severity, "dim")
    
    console.print(Panel(
        f"[{color}][{severity.upper()}][/{color}] {title}" +
        (f"\n{description}" if description else ""),
        title="[bold magenta]🔍 Finding[/bold magenta]",
        border_style="magenta",
        padding=(0, 1),
    ))


def print_progress(progress_text: str):
    """Display the VAPT progress tracker."""
    console.print(Panel(
        Text(progress_text),
        title="[bold cyan]📊 VAPT Progress[/bold cyan]",
        border_style="cyan",
        padding=(0, 1),
    ))


def print_error(message: str):
    """Display an error message."""
    console.print(f"  [bold red]✗ {message}[/bold red]")


def print_info(message: str):
    """Display an info message."""
    console.print(f"  [dim cyan]ℹ {message}[/dim cyan]")


def print_status(message: str):
    """Display a status message."""
    console.print(f"  [dim]{message}[/dim]")


def print_success(message: str):
    """Display a success message."""
    console.print(f"  [bold green]✓ {message}[/bold green]")


def get_user_input() -> str:
    """Get input from the user with a styled prompt."""
    try:
        return console.input("[bold cyan]CVA ❯ [/bold cyan]")
    except (EOFError, KeyboardInterrupt):
        return "/exit"


def get_approval() -> str:
    """Get user approval for a tool call."""
    console.print(
        "\n  [bold yellow]↵ Enter[/bold yellow] to approve  •  "
        "[bold]Type alternative[/bold] to redirect  •  "
        "[bold red]skip[/bold red] to skip\n"
    )
    try:
        response = console.input("[bold yellow]Action ❯ [/bold yellow]").strip()
        return response
    except (EOFError, KeyboardInterrupt):
        return "skip"


def print_separator():
    """Print a visual separator."""
    console.print(Rule(style="dim"))
