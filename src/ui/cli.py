"""CVA Rich Terminal UI — Gemini CLI-style chatbot interface."""

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.text import Text
from rich.table import Table
from rich.rule import Rule
from rich.columns import Columns
from rich.progress import Progress, SpinnerColumn, TextColumn

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style
from prompt_toolkit.history import InMemoryHistory

from src.brain.thinking import parse_thinking
from src.config import settings


console = Console()

# ── Slash Command Registry ────────────────────────────────────────────────────
# These mirror the commands defined in src/ui/commands.py.
# Update both places if you add a new slash command.
SLASH_COMMANDS = {
    "/help":       "Show all available commands",
    "/auto":       "Autonomous VAPT  /auto http://target:port",
    "/model":      "Switch LLM model  e.g. /model ollama:qwen3:8b",
    "/mode":       "Switch agent mode  /mode supervisor|single",
    "/agent":      "Show active specialist agent",
    "/debug":      "Toggle debug mode  /debug on|off",
    "/think":      "Show/hide LLM reasoning  /think on|off",
    "/rawtools":   "Show/hide raw tool output  /rawtools on|off",
    "/approval":   "Toggle tool call approval gate  /approval on|off",
    "/guardrails": "Toggle input guardrails  /guardrails on|off",
    "/tools":      "List all available MCP tools",
    "/sessions":   "Manage sessions  list|new|load|save|delete",
    "/run":        "Execute a raw shell command (injected into agent context)",
    "/report":     "Generate pentest report  md|html|both",
    "/progress":   "Show VAPT phase progress",
    "/findings":   "Show all findings from current session",
    "/target":     "Set the pentest target  e.g. /target 192.168.1.1",
    "/bg":         "Background tasks  /bg [list|status <id>]",
    "/log":        "View current session log  /log [tail N]",
    "/kb":         "Knowledge base  /kb [status|search|update]",
    "/settings":   "Show current settings",
    "/clear":      "Clear the screen",
    "/exit":       "Exit CVA",
}

# ── Prompt-toolkit completer ──────────────────────────────────────────────────

class _SlashCommandCompleter(Completer):
    """Show dropdown completions only when the input line starts with '/'."""

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.lstrip()
        # Only complete when the line starts with /
        if not text.startswith("/"):
            return
        # The word being typed is everything up to the first space
        word = text.split()[0] if " " in text else text
        for cmd, desc in SLASH_COMMANDS.items():
            if cmd.startswith(word):
                yield Completion(
                    cmd,
                    start_position=-len(word),
                    display=cmd,
                    display_meta=desc,
                )


_COMPLETER = _SlashCommandCompleter()

_PROMPT_STYLE = Style.from_dict({
    # The prompt itself
    "prompt":          "bold ansicyan",
    # Completion menu
    "completion-menu.completion":          "bg:#1c1c2e #c0c0d0",
    "completion-menu.completion.current":  "bg:#4040a0 bold #ffffff",
    "completion-menu.meta.completion":     "bg:#101020 #707080",
    "completion-menu.meta.completion.current": "bg:#303080 #a0a0c0",
    # Scrollbar
    "scrollbar.background":   "bg:#1c1c2e",
    "scrollbar.button":       "bg:#4040a0",
})

_PROMPT_LABEL = HTML("<prompt>CVA ❯ </prompt>")

_session = PromptSession(
    completer=_COMPLETER,
    complete_while_typing=True,
    style=_PROMPT_STYLE,
    history=InMemoryHistory(),
    mouse_support=False,
)

# ─────────────────────────────────────────────────────────────────────────────


def print_banner():
    """Display the CVA startup banner."""
    banner = Text()
    banner.append("╔══════════════════════════════════════════════════════════════╗\n", style="bold cyan")
    banner.append("║  ", style="bold cyan")
    banner.append("CVA", style="bold white")
    banner.append(" — Cognitive VAPT Assistant v3                       ", style="dim white")
    banner.append("║\n", style="bold cyan")
    banner.append("║  ", style="bold cyan")
    banner.append("Multi-Agent Pentesting • Supervisor + Specialists", style="dim white")
    banner.append("     ║\n", style="bold cyan")
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

    # Show thinking panel when explicitly enabled via /think on  (independent of debug_mode)
    if result.thinking and settings.show_thinking:
        print_thinking(result.thinking)

    if result.content:
        console.print(Panel(
            Markdown(result.content),
            title="[bold green]🤖 CVA[/bold green]",
            border_style="green",
            padding=(1, 2),
        ))


def print_tool_call(tool_name: str, tool_args: dict):
    """Display a proposed tool call with all arguments formatted clearly."""
    from rich.table import Table

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Key",   style="bold yellow", no_wrap=True)
    table.add_column("Value", style="white")
    for k, v in tool_args.items():
        table.add_row(k, str(v))

    console.print(Panel(
        table if tool_args else Text("(no arguments)", style="dim"),
        title=f"[bold yellow]🔧 {tool_name}[/bold yellow]",
        subtitle="[dim]human-in-the-loop approval required[/dim]",
        border_style="yellow",
        padding=(0, 1),
    ))


def get_tool_approval(tool_name: str, tool_args: dict) -> str:
    """Show the proposed tool call and ask the user for approval.

    Returns:
        "approve"  — run the tool as-is
        "skip"     — skip this tool call; agent receives a denial notice
        str        — custom feedback the agent sees as the tool "result"
    """
    print_tool_call(tool_name, tool_args)
    console.print(
        "  [dim]↵ / [bold]y[/bold] = approve  •  "
        "[bold]n[/bold] = deny  •  "
        "type custom feedback ↵[/dim]"
    )
    try:
        response = console.input(
            "  [bold yellow]Allow? ❯ [/bold yellow]"
        ).strip()
    except (EOFError, KeyboardInterrupt):
        console.print()
        return "skip"

    if response.lower() in ("", "y", "yes", "approve", "ok"):
        console.print("  [bold green]✓ Approved[/bold green]")
        return "approve"
    elif response.lower() in ("n", "no", "skip", "s", "deny"):
        console.print("  [bold red]✗ Denied[/bold red]")
        return "skip"
    else:
        console.print(f"  [dim]↩ Sending feedback to agent[/dim]")
        return response



_ERROR_SIGNALS = (
    "error", "exception", "traceback", "failed", "failure",
    "not found", "command not found", "permission denied",
    "no such file", "connection refused", "timeout", "killed",
    "stderr", "exit code", "returncode",
)


def _looks_like_error(text: str) -> bool:
    """Heuristic: does this tool result contain error content?"""
    low = text.lower()
    return any(sig in low for sig in _ERROR_SIGNALS)


def _render_tool_output(result: str) -> Text:
    """Render tool output text, highlighting lines that look like errors."""
    snippet = result[:5000]
    rendered = Text()
    for line in snippet.splitlines(keepends=True):
        low = line.lower()
        if any(sig in low for sig in _ERROR_SIGNALS):
            rendered.append(line, style="bold red")
        else:
            rendered.append(line, style="dim")
    if len(result) > 5000:
        rendered.append(f"\n... ({len(result) - 5000} more chars)", style="dim")
    return rendered


def print_tool_result(tool_name: str, result: str):
    """Display tool execution result.

    - show_tool_output ON  → always show full output; errors highlighted red
    - show_tool_output OFF → show brief summary, but still surface errors
    """
    is_error = _looks_like_error(result)

    if settings.show_tool_output:
        console.print(Panel(
            _render_tool_output(result),
            title=(
                f"[bold red]⚠ Error Output: {tool_name}[/bold red]"
                if is_error else
                f"[dim]📋 Raw Output: {tool_name}[/dim]"
            ),
            border_style="red" if is_error else "dim",
            padding=(0, 1),
        ))
    elif is_error:
        # Even when raw output is hidden, always surface errors
        snippet = result[:800].strip()
        overflow = f"\n... ({len(result) - 800} more chars)" if len(result) > 800 else ""
        console.print(Panel(
            Text(snippet + overflow, style="bold red"),
            title=f"[bold red]⚠ Tool Error: {tool_name}[/bold red]",
            border_style="red",
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


def print_status(message: str, style: str = "dim"):
    """Display a status message."""
    console.print(f"  [{style}]{message}[/{style}]")


def print_success(message: str):
    """Display a success message."""
    console.print(f"  [bold green]✓ {message}[/bold green]")


# ── Live thinking stream ──────────────────────────────────────────────────────

# All opening/closing tag pairs recognised by parse_thinking
_THINK_TAGS: list[tuple[str, str]] = [
    ("<think>",               "</think>"),
    ("<thinking>",            "</thinking>"),
    ("<reason>",              "</reason>"),
    ("<reasoning>",           "</reasoning>"),
    ("<|begin_of_thought|>",  "<|end_of_thought|>"),
]
# Longest possible opening tag — used for lookahead buffer
_MAX_OPEN_LEN = max(len(o) for o, _ in _THINK_TAGS)


def stream_agent_response(chunk_iter) -> dict:
    """Consume a LangGraph stream_mode='messages' iterator and display
    any <think> / <reasoning> block live as it streams.

    Returns:
        {"content": str, "tool_results": list[dict]}
    """
    from langchain_core.messages import AIMessageChunk, ToolMessage

    token_buf     = ""    # partial lookahead buffer
    response_buf  = ""    # non-thinking final response
    tool_results  = []

    in_think       = False    # currently inside a thinking block
    think_done     = False    # a thinking block was already seen and closed
    close_tag      = ""       # </...> tag we're looking for
    header_shown   = False    # has the ╭─ Thinking ─╮ header been printed?

    for chunk, _ in chunk_iter:
        # ── Collect tool results from the tools node ───────────────────────
        if isinstance(chunk, ToolMessage):
            tool_results.append({"name": chunk.name, "content": chunk.content})
            continue

        if not isinstance(chunk, AIMessageChunk):
            continue

        raw = chunk.content
        if isinstance(raw, list):
            # Structured content block (e.g. Claude-style)
            raw = "".join(
                b.get("text", "") if isinstance(b, dict) else "" for b in raw
            )
        if not isinstance(raw, str) or not raw:
            continue

        token_buf += raw

        # ── State machine ──────────────────────────────────────────────────
        while token_buf:
            if not in_think and not think_done:
                # Look for any opening tag
                best_idx, best_open, best_close = -1, "", ""
                for open_tag, close_tag_cand in _THINK_TAGS:
                    idx = token_buf.find(open_tag)
                    if idx != -1 and (best_idx == -1 or idx < best_idx):
                        best_idx, best_open, best_close = idx, open_tag, close_tag_cand

                if best_idx == -1:
                    # No opening tag — flush everything except lookahead tail
                    safe = max(0, len(token_buf) - _MAX_OPEN_LEN)
                    response_buf += token_buf[:safe]
                    token_buf = token_buf[safe:]
                    break

                # Found an opening tag
                response_buf += token_buf[:best_idx]
                token_buf = token_buf[best_idx + len(best_open):]
                in_think  = True
                close_tag = best_close

                if not header_shown:
                    header_shown = True
                    console.print()
                    console.print(
                        "[dim cyan]╭─ 💭 Thinking " + "─" * 46 + "╮[/dim cyan]"
                    )

            elif in_think:
                idx = token_buf.find(close_tag)
                if idx == -1:
                    # Closing tag hasn't arrived — stream everything live
                    console.print(
                        token_buf, end="", style="dim italic",
                        markup=False, highlight=False,
                    )
                    token_buf = ""
                    break

                # Closing tag found — flush last thinking chunk, close panel
                console.print(
                    token_buf[:idx], end="", style="dim italic",
                    markup=False, highlight=False,
                )
                console.print()
                console.print(
                    "[dim cyan]╰" + "─" * 60 + "╯[/dim cyan]\n"
                )
                token_buf  = token_buf[idx + len(close_tag):]
                in_think   = False
                think_done = True

            else:
                # After thinking block — rest is the final response
                response_buf += token_buf
                token_buf = ""
                break

    # ── Flush remainder ────────────────────────────────────────────────────
    if token_buf:
        if in_think:
            console.print(
                token_buf, end="", style="dim italic",
                markup=False, highlight=False,
            )
            console.print()
            console.print("[dim cyan]╰" + "─" * 60 + "╯[/dim cyan]\n")
        else:
            response_buf += token_buf

    return {"content": response_buf.strip(), "tool_results": tool_results}


def get_user_input() -> str:
    """Get input from the user with autocomplete for slash commands.

    Ctrl+C on an empty prompt exits CVA (/exit).
    Ctrl+C mid-line clears the current input and redisplays the prompt.
    Ctrl+D always exits.
    """
    try:
        text = _session.prompt(_PROMPT_LABEL, style=_PROMPT_STYLE)
        return text
    except KeyboardInterrupt:
        # If the user typed nothing, treat Ctrl+C as an exit request.
        # If they were mid-line, prompt_toolkit already cleared it; just
        # return empty so main.py continues and shows the prompt again.
        buf = _session.default_buffer.text if hasattr(_session, "default_buffer") else ""
        if not buf:
            # Empty prompt — exit
            return "/exit"
        return ""
    except EOFError:
        # Ctrl+D — always exit
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
