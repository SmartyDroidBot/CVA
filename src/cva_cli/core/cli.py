"""Typer-powered CLI entry point"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console

from ..agents import get_agent, list_agents, register_config
from ..agents.base import AgentConfig as RuntimeAgentConfig
from ..backends import GenerationConfig, get_backend, list_backends
from ..config import AppConfig, ConfigManager, save_config
from ..mcp import get_mcp_tools, get_tool
from .controller import (
    ensure_mcp,
    handle_list_models,
    handle_interaction,
    handle_chat_loop,
    handle_tool_execution
)


app = typer.Typer(
    add_completion=False, 
    no_args_is_help=False,
    context_settings={"allow_interspersed_args": True}
)


@dataclass
class RuntimeState:
    config_manager: ConfigManager
    config: AppConfig
    console: Console = field(default_factory=Console)
    mcp_initialized: bool = False
    tool_support_enabled: bool = False


def _build_console(config: AppConfig) -> Console:
    color_system = "auto" if config.color_output else None
    return Console(color_system=color_system)


def _print_error(state: RuntimeState, message: str):
    state.console.print(f"[bold red]Error:[/bold red] {message}")


@app.callback(invoke_without_command=True)
def _root_command(
    ctx: typer.Context,
    prompt: Optional[str] = typer.Argument(None, help="Prompt to execute"),
    config: Optional[Path] = typer.Option(None, "--config", help="Path to configuration file"),
    init_config: bool = typer.Option(False, "--init-config", help="Initialize default configuration"),
    backend_name: Optional[str] = typer.Option(None, "--backend", "-b", help="Backend to use"),
    url: Optional[str] = typer.Option(None, "--url", help="Backend URL"),
    model: Optional[str] = typer.Option(None, "--model", help="Model name"),
    agent_name: Optional[str] = typer.Option(None, "--agent", "-a", help="Agent to use"),
    temperature: Optional[float] = typer.Option(None, "--temperature", "-t", help="Sampling temperature"),
    max_tokens: Optional[int] = typer.Option(None, "--max-tokens", help="Maximum tokens to generate"),
    no_stream: bool = typer.Option(False, "--no-stream", help="Disable streaming output"),
    chat_mode: bool = typer.Option(False, "--chat", "-c", help="Interactive chat mode"),
    prompt_file: Optional[Path] = typer.Option(None, "--file", "-f", help="Read prompt from file"),
    list_models: bool = typer.Option(False, "--list-models", "-l", help="List available models"),
    list_backends_flag: bool = typer.Option(False, "--list-backends", help="List available backends"),
    list_agents_flag: bool = typer.Option(False, "--list-agents", help="List available agents"),
    list_tools_flag: bool = typer.Option(False, "--list-tools", help="List available MCP tools"),
    tool_info: Optional[str] = typer.Option(None, "--tool-info", help="Show info about a specific tool"),
    use_tool: Optional[str] = typer.Option(None, "--use-tool", help="Execute a tool"),
    tool_params: Optional[List[str]] = typer.Option(None, "--tool-params", help="Tool parameters key=value"),
    system_prompt: Optional[str] = typer.Option(None, "--system", help="Override system prompt"),
    verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output"),
    show_thinking: bool = typer.Option(False, "--show-thinking", help="Include think blocks in the output"),
):
    manager = ConfigManager(config)
    app_config = manager.load()
    if verbose:
        app_config.verbose = True

    # Register agents from config
    for name, cfg in app_config.agents.items():
        runtime_config = RuntimeAgentConfig(
            name=name,
            description=cfg.description,
            system_prompt=cfg.system_prompt or "",
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
            preferred_model=cfg.preferred_model
        )
        register_config(runtime_config)

    console = _build_console(app_config)
    state = RuntimeState(config_manager=manager, config=app_config, console=console)
    ctx.obj = state

    if init_config:
        default_config = AppConfig.default()
        if save_config(default_config, manager.config_path):
            console.print(f"Configuration initialized at: {manager.config_path}")
        else:
            _print_error(state, "Failed to initialize configuration")
        raise typer.Exit()

    if list_backends_flag:
        console.print("Available backends:")
        for name in list_backends():
            console.print(f"  - {name}")
        raise typer.Exit()

    if list_agents_flag:
        console.print("Available agents:")
        for item in list_agents() or []:
            if isinstance(item, tuple):
                console.print(f"  {item[0]}: {item[1]}")
            else:
                console.print(f"  {item}")
        raise typer.Exit()

    tool_flags_requested = list_tools_flag or tool_info or use_tool
    if tool_flags_requested or state.config.mcp_servers:
        ensure_mcp(state)

    if list_tools_flag:
        console.print("Available tools from MCP servers:")
        tools = get_mcp_tools()
        if not tools:
            console.print("  No tools available")
        else:
            grouped: Dict[str, List] = {}
            for tool in tools:
                grouped.setdefault(tool.server_name, []).append(tool)
            for server_name, server_tools in sorted(grouped.items()):
                console.print(f"\n  Server: {server_name}")
                for tool in server_tools:
                    console.print(f"    {tool.name:20s} - {tool.description}")
        raise typer.Exit()

    if tool_info:
        tool_entry = get_tool(tool_info)
        if not tool_entry:
            _print_error(state, f"Tool '{tool_info}' not found")
            raise typer.Exit(code=1)
        console.print(f"Tool: {tool_entry.name}")
        console.print(f"Server: {tool_entry.server_name}")
        console.print(f"Description: {tool_entry.description}")
        params = tool_entry.get_parameters()
        console.print("\nParameters:")
        if not params:
            console.print("  (none)")
        else:
            for param in params:
                required = " (required)" if param.get("required") else ""
                default = (
                    f" [default: {param.get('default')}]" if param.get("default") is not None else ""
                )
                console.print(f"  {param['name']:15s} ({param['type']}){required}{default}")
                if param.get("description"):
                    console.print(f"    {param['description']}")
        raise typer.Exit()

    if use_tool:
        handle_tool_execution(state, use_tool, tool_params)
        raise typer.Exit()

    prompt_text: Optional[str] = None
    if prompt_file:
        try:
            prompt_text = prompt_file.read_text(encoding="utf-8")
        except Exception as exc:
            _print_error(state, f"Failed to read file: {exc}")
            raise typer.Exit(code=1)
    elif prompt:
        prompt_text = prompt
    elif not sys.stdin.isatty():
        prompt_text = sys.stdin.read().strip()

    if not prompt_text and not chat_mode:
        chat_mode = True

    agent_id = agent_name or state.config.default_agent
    try:
        agent = get_agent(agent_id)
    except Exception as exc:
        _print_error(state, str(exc))
        raise typer.Exit(code=1)

    agent_cfg = state.config.agents.get(agent_id)
    backend_type = backend_name or state.config.backend.type
    backend_url = url or state.config.backend.url
    chosen_model = (
        model
        or (agent_cfg.preferred_model if agent_cfg and agent_cfg.preferred_model else None)
        or state.config.backend.default_model
    )

    backend = get_backend(backend_type, model=chosen_model, base_url=backend_url)

    generation_config = GenerationConfig(
        temperature=temperature or (agent_cfg.temperature if agent_cfg else 0.7),
        max_tokens=max_tokens or (agent_cfg.max_tokens if agent_cfg else None),
        stream=not no_stream,
    )

    if list_models:
        handle_list_models(state, backend)
        raise typer.Exit()

    if chat_mode:
        handle_chat_loop(state, backend, agent, chosen_model, generation_config, system_prompt, show_thinking)
    elif prompt_text:
        handle_interaction(
            state,
            backend,
            agent,
            chosen_model,
            generation_config,
            prompt_text,
            system_prompt,
            show_thinking,
        )
    else:
        _print_error(state, "No action specified. Provide a prompt or use --chat")
        raise typer.Exit(code=1)


def main():  # pragma: no cover - console script wrapper
    app()
