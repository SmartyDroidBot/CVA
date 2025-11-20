"""Utility helpers that let the CLI coordinate MCP tool usage."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from rich.console import Console

from ..backends import GenerationConfig, Message
from . import execute_tool, get_mcp_tools

_TOOL_CALL_PATTERN = re.compile(r"<<CALL_TOOL\s+([A-Za-z0-9_\-:.]+)\s+(\{.*?\})>>", re.DOTALL)
_MAX_TOOL_CALLS = 3


def augment_system_prompt(tool_support_enabled: bool, base_prompt: Optional[str]) -> Optional[str]:
    if not tool_support_enabled:
        return base_prompt
    instructions = _build_tool_instruction_prompt()
    if not instructions:
        return base_prompt
    if base_prompt:
        return f"{base_prompt}\n\n{instructions}"
    return instructions


def process_response_with_tools(
    console: Console,
    tool_support_enabled: bool,
    backend,
    conversation: List[Message],
    response,
    model: str,
    config: GenerationConfig,
) -> Tuple[str, Optional[Dict[str, int]]]:
    response_text = response.content
    latest_usage = response.usage
    if not tool_support_enabled:
        sanitized = response_text.strip()
        conversation.append(Message(role="assistant", content=sanitized))
        return sanitized, latest_usage

    display_chunks: List[str] = []
    tool_calls_executed = 0

    while True:
        sanitized = _strip_tool_directives(response_text)
        if sanitized:
            display_chunks.append(sanitized)
            conversation.append(Message(role="assistant", content=sanitized))

        calls = _parse_tool_calls(response_text)
        if not calls or tool_calls_executed >= _MAX_TOOL_CALLS:
            break

        for tool_name, args in calls:
            if tool_calls_executed >= _MAX_TOOL_CALLS:
                console.print(
                    "[yellow]Tool call limit reached; remaining directives will be ignored.[/yellow]"
                )
                break
            tool_calls_executed += 1
            console.print(
                f"[cyan]→ Calling tool '{tool_name}' with args: {json.dumps(args, ensure_ascii=False)}[/cyan]"
            )
            result = execute_tool(tool_name, **args)
            if result.get("success"):
                console.print(f"[green]✓ Tool '{tool_name}' succeeded[/green]")
            else:
                console.print(
                    f"[red]✗ Tool '{tool_name}' failed: {result.get('error', 'Unknown error')}[/red]"
                )
            feedback = _format_tool_feedback(tool_name, args, result)
            conversation.append(Message(role="user", content=feedback))

        if tool_calls_executed >= _MAX_TOOL_CALLS:
            break

        follow_up = backend.generate(model=model, messages=conversation, config=config)
        response_text = follow_up.content
        latest_usage = follow_up.usage

    if not display_chunks:
        sanitized = _strip_tool_directives(response_text)
        conversation.append(Message(role="assistant", content=sanitized))
        display_chunks.append(sanitized)

    final_output = "\n\n".join(chunk for chunk in display_chunks if chunk)
    return final_output, latest_usage


def _build_tool_instruction_prompt() -> Optional[str]:
    tools = get_mcp_tools()
    if not tools:
        return None
    lines = [
        "You can call MCP tools when needed. Emit tool calls using exactly this format (no prose around it):",
        "<<CALL_TOOL tool_name {\"argument\": \"value\"}>>",
        "After you receive the tool output you will be given an updated user message. Continue the conversation using that information.",
        "Available tools:",
    ]
    for item in tools:
        desc = item.description or "(no description provided)"
        lines.append(f"- {item.name} (server: {item.server_name}): {desc}")
    return "\n".join(lines)


def _strip_tool_directives(text: str) -> str:
    return _TOOL_CALL_PATTERN.sub("", text).strip()


def _parse_tool_calls(text: str) -> List[Tuple[str, Dict[str, Any]]]:
    calls: List[Tuple[str, Dict[str, Any]]] = []
    for match in _TOOL_CALL_PATTERN.finditer(text):
        name = match.group(1)
        raw_args = match.group(2)
        try:
            args = json.loads(raw_args)
        except json.JSONDecodeError:
            continue
        if isinstance(args, dict):
            calls.append((name, args))
    return calls


def _format_tool_feedback(tool_name: str, args: Dict[str, Any], result: Dict[str, Any]) -> str:
    status = "SUCCESS" if result.get("success") else "ERROR"
    output = result.get("output") if result.get("success") else result.get("error")
    output_text = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
    metadata = result.get("metadata")
    meta_text = f"\nMetadata: {json.dumps(metadata, ensure_ascii=False)}" if metadata else ""
    return (
        f"Tool {tool_name} returned {status}.\n"
        f"Arguments: {json.dumps(args, ensure_ascii=False)}\n"
        f"Output:\n{output_text or '(no output)'}{meta_text}\n"
        "Please continue assisting the user with this information."
    )


__all__ = [
    "augment_system_prompt",
    "process_response_with_tools",
]
