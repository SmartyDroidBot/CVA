import platform
from typing import Any, List, Optional, Dict
import re
import json
from rich.console import Console
from rich.prompt import Confirm

from ..backends.base import LLMBackend, GenerationConfig, Message
from ..mcp import get_mcp_tools, execute_tool

SYSTEM_INSTRUCTIONS = """Answer the following questions as best you can. You have access to the following tools:

{tools}

Current Operating System: {os_name}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question
"""

def run_react_agent(
    console: Console,
    backend: LLMBackend,
    agent: Any,
    model: str,
    config: GenerationConfig,
    prompt: str,
    system_override: Optional[str],
    show_thinking: bool
):
    # 1. Setup Tools
    mcp_tools = get_mcp_tools()
    tool_descriptions = "\n".join([f"{t.name}: {t.description}" for t in mcp_tools])
    tool_names = ", ".join([t.name for t in mcp_tools])
    
    # 2. Prepare Messages
    system_content = SYSTEM_INSTRUCTIONS.format(
        tools=tool_descriptions,
        tool_names=tool_names,
        os_name=platform.system()
    )
    
    if system_override or agent.config.system_prompt:
        sys_prompt = system_override or agent.config.system_prompt
        system_content = f"{sys_prompt}\n\n{system_content}"

    # Initial User Message
    # We append "Thought:" to prime the model to start thinking immediately
    user_content = f"Question: {prompt}\nThought:"
    
    messages = [
        Message(role="system", content=system_content),
        Message(role="user", content=user_content)
    ]

    console.print(f"[bold blue]Thinking...[/bold blue]")
    
    # Call LLM - First Turn
    # We add a stop sequence to prevent hallucinating the observation
    current_stop_sequences = config.stop_sequences or []
    if "Observation:" not in current_stop_sequences:
        config.stop_sequences = (current_stop_sequences + ["Observation:"])

    response = backend.generate(model=model, messages=messages, config=config)
    content = response.content
    
    # Restore config
    config.stop_sequences = current_stop_sequences

    # Clean content if it still contains Observation (in case stop sequence failed)
    if "Observation:" in content:
        content = content.split("Observation:")[0].strip()

    if show_thinking:
        console.print(f"[dim]{content}[/dim]")

    # Parse for Action
    action_match = re.search(r"Action:\s*(.*?)\nAction Input:\s*(.*)", content, re.DOTALL)
    
    if action_match:
        tool_name = action_match.group(1).strip()
        tool_input = action_match.group(2).strip()
        
        # Clean up tool input if it has extra newlines or text
        if "\n" in tool_input:
            tool_input = tool_input.split("\n")[0]

        console.print(f"\n[bold yellow]Tool Recommendation:[/bold yellow] {tool_name}")
        console.print(f"[yellow]Input:[/yellow] {tool_input}")
        
        # 3. Approval
        if Confirm.ask("Do you want to execute this tool?"):
            # 4. Run Tool
            console.print(f"[bold green]Executing {tool_name}...[/bold green]")
            
            # Parse input arguments
            tool_args = {}
            try:
                tool_args = json.loads(tool_input)
            except:
                target_tool = next((t for t in mcp_tools if t.name == tool_name), None)
                if target_tool:
                    params = target_tool.get_parameters()
                    if params and len(params) == 1:
                        tool_args = {params[0]['name']: tool_input}
                    else:
                        tool_args = {"command": tool_input}
            
            result = execute_tool(tool_name, **tool_args)
            
            output = ""
            if result.get("success"):
                output = result.get("output", "")
                console.print(f"\n[bold cyan]Tool Output:[/bold cyan]\n{output}")
            else:
                output = f"Error: {result.get('error')}"
                console.print(f"\n[bold red]Tool Failed:[/bold red]\n{output}")

            # 5. Inference & Next Steps
            console.print(f"\n[bold blue]Analyzing results...[/bold blue]")
            
            # Update history for the next turn
            messages.append(Message(role="assistant", content=content))
            messages.append(Message(role="user", content=f"Observation: {output}\nThought:"))
            
            next_response = backend.generate(model=model, messages=messages, config=config)
            
            console.print(f"\n[bold magenta]Inference & Next Steps:[/bold magenta]")
            console.print(next_response.content)
            
        else:
            console.print("[yellow]Tool execution cancelled.[/yellow]")
    else:
        console.print("\n[bold green]Response:[/bold green]")
        console.print(content)

    console.print("\n[bold]Interaction ended.[/bold]")
