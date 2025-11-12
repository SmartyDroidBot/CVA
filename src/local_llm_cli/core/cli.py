"""Main CLI interface"""

import argparse
import sys
from pathlib import Path
from typing import Optional

from ..backends import get_backend, list_backends, GenerationConfig
from ..agents import get_agent, list_agents
from ..mcp import get_mcp_manager, add_mcp_server, get_mcp_tools, get_tool, execute_tool


def print_error(message: str):
    """Print error message to stderr"""
    print(f"Error: {message}", file=sys.stderr)


def print_info(message: str):
    """Print info message"""
    print(message, file=sys.stderr)


def handle_list_models(backend):
    """Handle --list-models command"""
    try:
        models = backend.list_models()
        if models:
            print("Available models:")
            for model in models:
                size_info = ""
                if model.size:
                    size_gb = model.size / (1024**3)
                    size_info = f" ({size_gb:.2f} GB)"
                desc_info = f" - {model.description}" if model.description else ""
                print(f"  - {model.name}{size_info}{desc_info}")
        else:
            print("No models found or listing not supported for this backend")
    except Exception as e:
        print_error(f"Failed to list models: {e}")
        sys.exit(1)


def handle_chat_mode(backend, args):
    """Handle interactive chat mode"""
    # Get agent if specified
    agent = None
    if hasattr(args, 'agent') and args.agent:
        try:
            agent = get_agent(args.agent)
            print(f"Agent: {agent.name} - {agent.description}")
        except ValueError as e:
            print_error(str(e))
            sys.exit(1)
    
    print(f"Local LLM Chat (backend: {backend.backend_name}, model: {backend.model})")
    print("Type 'exit', 'quit', or Ctrl+C to exit")
    print("Type '/clear' to clear conversation history")
    if agent:
        print("Type '/agent <name>' to switch agents")
        print("Type '/agents' to list available agents")
    print("-" * 50)
    
    # Use agent's config if available
    if agent:
        config = agent.get_generation_config()
        config.stream = not args.no_stream
        system_prompt = agent.get_system_prompt()
    else:
        config = GenerationConfig(
            stream=not args.no_stream,
            temperature=args.temperature if hasattr(args, 'temperature') else 0.7
        )
        system_prompt = args.system if hasattr(args, 'system') else None
    
    try:
        while True:
            try:
                user_input = input("\nYou: ").strip()
                
                if user_input.lower() in ["exit", "quit"]:
                    print("Goodbye!")
                    break
                
                if user_input == "/clear":
                    backend.clear_history()
                    print("Conversation history cleared.")
                    continue
                
                if user_input.startswith("/agent "):
                    new_agent_name = user_input[7:].strip()
                    try:
                        agent = get_agent(new_agent_name)
                        config = agent.get_generation_config()
                        config.stream = not args.no_stream
                        system_prompt = agent.get_system_prompt()
                        backend.clear_history()  # Clear history when switching agents
                        print(f"Switched to agent: {agent.name} - {agent.description}")
                    except ValueError as e:
                        print_error(str(e))
                    continue
                
                if user_input == "/agents":
                    print("\nAvailable agents:")
                    for name, description in list_agents():
                        marker = " (current)" if agent and agent.name == name else ""
                        print(f"  {name}: {description}{marker}")
                    continue
                
                if not user_input:
                    continue
                
                # Preprocess input if using agent
                if agent:
                    user_input = agent.preprocess_input(user_input)
                
                print("\nAssistant: ", end="", flush=True)
                
                if config.stream:
                    response_text = ""
                    for chunk in backend.chat_stream(user_input, system=system_prompt, config=config):
                        print(chunk, end="", flush=True)
                        response_text += chunk
                    print()  # New line after streaming
                    
                    # Postprocess output if using agent
                    if agent:
                        response_text = agent.postprocess_output(response_text)
                else:
                    response = backend.chat(user_input, system=system_prompt, config=config)
                    
                    # Postprocess output if using agent
                    if agent:
                        response = agent.postprocess_output(response)
                    
                    print(response)
                
            except EOFError:
                print("\nGoodbye!")
                break
    except KeyboardInterrupt:
        print("\n\nGoodbye!")


def handle_single_prompt(backend, prompt, args):
    """Handle single prompt generation"""
    # Get agent if specified
    agent = None
    if hasattr(args, 'agent') and args.agent:
        try:
            agent = get_agent(args.agent)
        except ValueError as e:
            print_error(str(e))
            sys.exit(1)
    
    # Use agent's config if available
    if agent:
        config = agent.get_generation_config()
        config.stream = not args.no_stream
        system_prompt = agent.get_system_prompt()
        prompt = agent.preprocess_input(prompt)
    else:
        config = GenerationConfig(
            stream=not args.no_stream,
            temperature=args.temperature if hasattr(args, 'temperature') else 0.7
        )
        system_prompt = args.system if hasattr(args, 'system') else None
    
    try:
        if config.stream:
            response_text = ""
            for chunk in backend.generate_stream(prompt, system=system_prompt, config=config):
                print(chunk, end="", flush=True)
                response_text += chunk
            print()  # New line after streaming
            
            if agent:
                response_text = agent.postprocess_output(response_text)
        else:
            response = backend.generate(prompt, system=system_prompt, config=config)
            
            if agent:
                response = agent.postprocess_output(response)
            
            print(response)
    except Exception as e:
        print_error(str(e))
        sys.exit(1)


def get_prompt_from_sources(args) -> Optional[str]:
    """Get prompt from various sources (args, file, stdin)"""
    prompt = None
    
    # Try file first
    if args.file:
        try:
            prompt = args.file.read_text()
        except Exception as e:
            print_error(f"Failed to read file: {e}")
            sys.exit(1)
    # Then command line args
    elif args.prompt:
        prompt = " ".join(args.prompt)
    # Finally stdin/pipe
    elif not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
    
    return prompt


def handle_list_agents():
    """Handle --list-agents command"""
    print("Available agents:")
    for name, description in list_agents():
        print(f"  {name:20s} - {description}")


def handle_list_tools():
    """Handle --list-tools command"""
    print("Available tools from MCP servers:")
    tools = get_mcp_tools()
    
    if not tools:
        print("  No tools available.")
        print("  Built-in MCP servers should provide file, math, and system tools.")
        return
    
    # Group by server
    by_server = {}
    for tool in tools:
        server_name = tool.server_name
        if server_name not in by_server:
            by_server[server_name] = []
        by_server[server_name].append(tool)
    
    for server_name, server_tools in sorted(by_server.items()):
        print(f"\n  Server: {server_name}")
        for tool in server_tools:
            print(f"    {tool.name:20s} - {tool.description}")


def handle_use_tool(args):
    """Handle --use-tool command"""
    tool_name = args.use_tool
    
    tool = get_tool(tool_name)
    if not tool:
        print_error(f"Tool not found: {tool_name}")
        print_info("Use --list-tools to see available tools")
        sys.exit(1)
    
    # Show tool info
    print(f"Tool: {tool.name}")
    print(f"Description: {tool.description}")
    print(f"Category: {tool.category.value}")
    print("\nParameters:")
    for param in tool.parameters:
        required = "required" if param.required else "optional"
        default = f" (default: {param.default})" if param.default is not None else ""
        print(f"  {param.name} ({param.type}, {required}){default}")
        print(f"    {param.description}")
    
    # Parse tool parameters from remaining args
    tool_params = {}
    if args.tool_params:
        for param_str in args.tool_params:
            if "=" in param_str:
                key, value = param_str.split("=", 1)
                tool_params[key] = value
    
    if tool_params or not tool.parameters:
        print(f"\nExecuting with parameters: {tool_params}")
        result = execute_tool(tool_name, **tool_params)
        
        if result.success:
            print(f"\n✓ Success:")
            print(result.data)
            if result.metadata:
                print(f"\nMetadata: {result.metadata}")
        else:
            print_error(f"Tool execution failed: {result.error}")
            sys.exit(1)
    else:
        print("\nTo execute, provide parameters: --use-tool TOOL param1=value1 param2=value2")


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser"""
    parser = argparse.ArgumentParser(
        description="Local LLM CLI - Interact with local language models",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Simple prompt
  llm "What is the capital of France?"
  
  # Interactive chat mode
  llm --chat
  
  # Use an agent
  llm --agent coding "Write a Python function to sort a list"
  llm --agent creative "Write a short poem about the ocean"
  
  # Chat with an agent
  llm --chat --agent teacher
  
  # Use specific model
  llm --model llama2 "Explain quantum computing"
  
  # List available agents
  llm --list-agents
  
  # List available models
  llm --list-models
  
  # Use different backend
  llm --backend llama.cpp "Hello!"
        """
    )
    
    # Positional arguments
    parser.add_argument("prompt", nargs="*", help="Prompt to send to the LLM")
    
    # Backend options
    parser.add_argument("--model", "-m", help="Model to use")
    parser.add_argument(
        "--backend", "-b",
        default="ollama",
        help=f"Backend to use (available: {', '.join(list_backends())})"
    )
    parser.add_argument("--base-url", help="Base URL for the backend API")
    
    # Agent options
    parser.add_argument("--agent", "-a", help="Agent to use (e.g., coding, creative, teacher)")
    parser.add_argument("--list-agents", action="store_true", help="List available agents")
    
    # Tool options
    parser.add_argument("--list-tools", action="store_true", help="List available tools")
    parser.add_argument("--use-tool", help="Use a specific tool")
    parser.add_argument("--tool-params", nargs="*", help="Tool parameters (key=value)")
    
    # Mode options
    parser.add_argument("--chat", "-c", action="store_true", help="Start interactive chat mode")
    parser.add_argument("--list-models", "-l", action="store_true", help="List available models")
    
    # Input options
    parser.add_argument("--file", "-f", type=Path, help="Read prompt from file")
    parser.add_argument("--system", "-s", help="System prompt (overrides agent's system prompt)")
    
    # Generation options
    parser.add_argument("--no-stream", action="store_true", help="Disable streaming output")
    parser.add_argument("--temperature", "-t", type=float, default=0.7, help="Temperature (0.0-2.0)")
    
    return parser


def initialize_mcp_servers(config_file: Optional[Path] = None):
    """Initialize MCP servers from configuration"""
    mcp_manager = get_mcp_manager()
    
    # Get the path to built-in MCP servers
    mcp_servers_dir = Path(__file__).parent.parent / "mcp_servers"
    
    # Add built-in MCP servers
    builtin_servers = {
        "filesystem": mcp_servers_dir / "filesystem.py",
        "math": mcp_servers_dir / "math.py",
        "system": mcp_servers_dir / "system.py",
    }
    
    for server_name, server_path in builtin_servers.items():
        if server_path.exists():
            success = mcp_manager.add_server(
                server_name=server_name,
                command=sys.executable,  # Use current Python interpreter
                args=[str(server_path)]
            )
            if not success:
                print_info(f"Warning: Failed to load built-in MCP server: {server_name}")
    
    # TODO: In Phase 4, also load user-configured MCP servers from config file
    
    return mcp_manager


def load_mcp_tools():
    """Load tools from connected MCP servers"""
    # Tools are now accessed directly from MCP manager
    # No need for a separate registry
    pass


def main():
    """Main entry point"""
    parser = create_parser()
    args = parser.parse_args()
    
    # Initialize MCP servers and load tools
    initialize_mcp_servers()
    load_mcp_tools()
    
    # Initialize backend
    try:
        backend = get_backend(
            backend_name=args.backend,
            model=args.model,
            base_url=args.base_url
        )
    except ValueError as e:
        print_error(str(e))
        sys.exit(1)
    
    # Check backend health
    if not backend.health_check():
        print_error(f"Cannot connect to {backend.backend_name} at {backend.base_url}")
        if backend.backend_name == "ollama":
            print_info("Make sure Ollama is running: ollama serve")
        sys.exit(1)
    
    # Verify model exists (for non-list commands)
    if not args.list_models and backend.backend_name == "ollama":
        try:
            available_models = [m.name for m in backend.list_models()]
            if available_models and backend.model not in available_models:
                print_error(f"Model '{backend.model}' not found.")
                print_info(f"Available models: {', '.join(available_models)}")
                print_info(f"Pull it with: ollama pull {backend.model}")
                sys.exit(1)
        except:
            pass  # If we can't check, proceed anyway
    
    # Handle commands
    if args.list_agents:
        handle_list_agents()
        return
    
    if args.list_tools:
        handle_list_tools()
        return
    
    if args.use_tool:
        handle_use_tool(args)
        return
    
    if args.list_models:
        handle_list_models(backend)
        return
    
    if args.chat:
        handle_chat_mode(backend, args)
        return
    
    # Get prompt for single generation
    prompt = get_prompt_from_sources(args)
    
    if not prompt:
        parser.print_help()
        sys.exit(1)
    
    # Generate response
    handle_single_prompt(backend, prompt, args)


if __name__ == "__main__":
    main()
