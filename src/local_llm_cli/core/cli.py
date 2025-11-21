"""Typer-powered CLI entry point"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import typer
from rich.console import Console

from ..agents import get_agent, list_agents, register_config
from ..agents.base import AgentConfig as RuntimeAgentConfig
from ..backends import GenerationConfig, Message, get_backend, list_backends
from ..config import AppConfig, ConfigManager, save_config
from ..mcp import add_mcp_server, execute_tool, get_mcp_tools, get_tool
from ..mcp.tool_runtime import augment_system_prompt, process_response_with_tools


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


def _get_state(ctx: typer.Context) -> RuntimeState:
    state = ctx.obj
    if not isinstance(state, RuntimeState):
        raise RuntimeError("Runtime state has not been initialized")
    return state


def _initialize_mcp_servers(config: AppConfig):
    for server_name, server_config in config.mcp_servers.items():
        if not server_config.enabled:
            continue
        success = add_mcp_server(
            server_name=server_name,
            command=server_config.command,
            args=server_config.args,
            connection_type=server_config.type,
            url=server_config.url,
            headers=server_config.headers,
            env=server_config.env,
        )
        if not success and config.verbose:
            print(f"Warning: Failed to load MCP server: {server_name}", file=sys.stderr)


def _ensure_mcp(state: RuntimeState):
    if state.mcp_initialized:
        return
    _initialize_mcp_servers(state.config)
    state.mcp_initialized = True
    state.tool_support_enabled = bool(get_mcp_tools())


def _print_error(state: RuntimeState, message: str):
    state.console.print(f"[bold red]Error:[/bold red] {message}", file=sys.stderr)


def _handle_list_models(state: RuntimeState, backend):
    try:
        models = backend.list_models()
        if not models:
            state.console.print("No models found or listing not supported for this backend")
            return
        state.console.print("Available models:")
        for model in models:
            size_info = f" ({model.size / (1024**3):.2f} GB)" if model.size else ""
            desc_info = f" - {model.description}" if model.description else ""
            state.console.print(f"  - {model.name}{size_info}{desc_info}")
    except Exception as exc:  # pragma: no cover - backend errors
        _print_error(state, f"Failed to list models: {exc}")
        raise typer.Exit(code=1)


def _handle_chat_mode(
    state: RuntimeState,
    backend,
    agent,
    model: str,
    config: GenerationConfig,
    system_override: Optional[str],
    show_thinking: bool,
):
    console = state.console
    console.print(f"[info]Starting chat mode with model: {model}")
    console.print(f"[info]Using agent: {agent.config.name}")
    console.print("Type 'exit'/'quit' to end, 'clear' to reset conversation")
    console.print("=" * 50)

    conversation: List[Message] = []
    system_prompt = augment_system_prompt(
        state.tool_support_enabled,
        system_override or agent.config.system_prompt,
    )
    if system_prompt:
        conversation.append(Message(role="system", content=system_prompt))

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            console.print("\nGoodbye!")
            break
        if user_input.lower() == "clear":
            conversation = []
            if system_prompt:
                conversation.append(Message(role="system", content=system_prompt))
            console.print("\nConversation cleared.\n")
            continue

        conversation.append(Message(role="user", content=user_input))
        console.print("\nAssistant: ", end="", flush=True)
        try:
            response = backend.generate(model=model, messages=conversation, config=config)
        except Exception as exc:  # pragma: no cover - backend error path
            console.print(f"\nError: {exc}\n")
            conversation.pop()
            continue

        output_text, _ = process_response_with_tools(
            console=console,
            tool_support_enabled=state.tool_support_enabled,
            backend=backend,
            conversation=conversation,
            response=response,
            model=model,
            config=config,
        )

        if not show_thinking:
            output_text = re.sub(r"<think>.*?</think>", "", output_text, flags=re.DOTALL).strip()

        console.print(output_text)


def _handle_single_prompt(
    state: RuntimeState,
    backend,
    agent,
    model: str,
    config: GenerationConfig,
    prompt: str,
    system_override: Optional[str],
    show_thinking: bool,
):
    console = state.console
    system_prompt = augment_system_prompt(
        state.tool_support_enabled,
        system_override or agent.config.system_prompt,
    )
    conversation: List[Message] = []
    if system_prompt:
        conversation.append(Message(role="system", content=system_prompt))
    conversation.append(Message(role="user", content=prompt))
    try:
        response = backend.generate(model=model, messages=conversation, config=config)
    except Exception as exc:
        _print_error(state, str(exc))
        raise typer.Exit(code=1)

    output_text, usage = process_response_with_tools(
        console=console,
        tool_support_enabled=state.tool_support_enabled,
        backend=backend,
        conversation=conversation,
        response=response,
        model=model,
        config=config,
    )

    if not show_thinking:
        output_text = re.sub(r"<think>.*?</think>", "", output_text, flags=re.DOTALL).strip()

    console.print("\n" + "=" * 50)
    console.print(output_text)
    console.print("=" * 50 + "\n")
    if usage:
        total = usage.get("total_tokens", "N/A")
        console.print(f"[info]Tokens used: {total}")


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
        _ensure_mcp(state)

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
        params: Dict[str, str] = {}
        for param in tool_params or []:
            try:
                key, value = param.split("=", 1)
                params[key.strip()] = value.strip()
            except ValueError:
                _print_error(state, f"Invalid tool parameter format: {param}. Use key=value.")
                raise typer.Exit(code=1)

        result = execute_tool(use_tool, **params)
        if result.get("success"):
            console.print("\n✓ Success:")
            if output := result.get("output"):
                console.print(output)
            metadata = result.get("metadata")
            if metadata:
                console.print(f"\nMetadata: {metadata}")
        else:
            _print_error(state, result.get("error", "Tool execution failed"))
            raise typer.Exit(code=1)
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
        _handle_list_models(state, backend)
        raise typer.Exit()

    if chat_mode:
        _handle_chat_mode(state, backend, agent, chosen_model, generation_config, system_prompt, show_thinking)
    elif prompt_text:
        _handle_single_prompt(
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
