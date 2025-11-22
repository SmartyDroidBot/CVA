from __future__ import annotations

import sys
import re
from typing import List, Optional, Dict
from rich.console import Console
import typer

from ..config import AppConfig
from ..backends import GenerationConfig, Message, get_backend
from ..mcp import add_mcp_server, get_mcp_tools, execute_tool
from ..agents.react import run_react_agent

def initialize_mcp_servers(config: AppConfig, verbose: bool = False):
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
        if not success and verbose:
            print(f"Warning: Failed to load MCP server: {server_name}", file=sys.stderr)

def ensure_mcp(state):
    if state.mcp_initialized:
        return
    initialize_mcp_servers(state.config, state.config.verbose)
    state.mcp_initialized = True
    state.tool_support_enabled = bool(get_mcp_tools())

def handle_list_models(state, backend):
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
    except Exception as exc:
        state.console.print(f"[bold red]Error:[/bold red] Failed to list models: {exc}")
        raise typer.Exit(code=1)

def handle_interaction(
    state,
    backend,
    agent,
    model: str,
    config: GenerationConfig,
    prompt: str,
    system_override: Optional[str],
    show_thinking: bool,
):
    """
    Handles a single interaction using the ReAct agent pattern.
    """
    console = state.console
    
    # Ensure MCP is initialized for tools
    ensure_mcp(state)
    
    # Run the ReAct agent
    run_react_agent(
        console=console,
        backend=backend,
        agent=agent,
        model=model,
        config=config,
        prompt=prompt,
        system_override=system_override,
        show_thinking=show_thinking
    )

def handle_tool_execution(state, tool_name: str, tool_params: List[str]):
    ensure_mcp(state)
    
    params: Dict[str, str] = {}
    for param in tool_params or []:
        try:
            key, value = param.split("=", 1)
            params[key.strip()] = value.strip()
        except ValueError:
            state.console.print(f"[bold red]Error:[/bold red] Invalid tool parameter format: {param}. Use key=value.")
            raise typer.Exit(code=1)

    result = execute_tool(tool_name, **params)
    if result.get("success"):
        state.console.print("\n✓ Success:")
        if output := result.get("output"):
            state.console.print(output)
        metadata = result.get("metadata")
        if metadata:
            state.console.print(f"\nMetadata: {metadata}")
    else:
        state.console.print(f"[bold red]Error:[/bold red] {result.get('error', 'Tool execution failed')}")
        raise typer.Exit(code=1)

def handle_chat_loop(
    state,
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
            console.print("\nConversation cleared (stateless).\n")
            continue

        handle_interaction(
            state=state,
            backend=backend,
            agent=agent,
            model=model,
            config=config,
            prompt=user_input,
            system_override=system_override,
            show_thinking=show_thinking
        )
