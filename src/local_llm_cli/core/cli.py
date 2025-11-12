"""Main CLI interface"""

import argparse
import sys
from pathlib import Path
from typing import Optional

from ..backends import get_backend, list_backends, GenerationConfig


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
    print(f"Local LLM Chat (backend: {backend.backend_name}, model: {backend.model})")
    print("Type 'exit', 'quit', or Ctrl+C to exit")
    print("Type '/clear' to clear conversation history")
    print("-" * 50)
    
    config = GenerationConfig(
        stream=not args.no_stream,
        temperature=args.temperature if hasattr(args, 'temperature') else 0.7
    )
    
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
                
                if not user_input:
                    continue
                
                print("\nAssistant: ", end="", flush=True)
                
                if config.stream:
                    for chunk in backend.chat_stream(user_input, system=args.system, config=config):
                        print(chunk, end="", flush=True)
                    print()  # New line after streaming
                else:
                    response = backend.chat(user_input, system=args.system, config=config)
                    print(response)
                
            except EOFError:
                print("\nGoodbye!")
                break
    except KeyboardInterrupt:
        print("\n\nGoodbye!")


def handle_single_prompt(backend, prompt, args):
    """Handle single prompt generation"""
    config = GenerationConfig(
        stream=not args.no_stream,
        temperature=args.temperature if hasattr(args, 'temperature') else 0.7
    )
    
    try:
        if config.stream:
            for chunk in backend.generate_stream(prompt, system=args.system, config=config):
                print(chunk, end="", flush=True)
            print()  # New line after streaming
        else:
            response = backend.generate(prompt, system=args.system, config=config)
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
  
  # Use specific model
  llm --model llama2 "Explain quantum computing"
  
  # Pipe input
  echo "Summarize this text" | llm
  
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
    
    # Mode options
    parser.add_argument("--chat", "-c", action="store_true", help="Start interactive chat mode")
    parser.add_argument("--list-models", "-l", action="store_true", help="List available models")
    
    # Input options
    parser.add_argument("--file", "-f", type=Path, help="Read prompt from file")
    parser.add_argument("--system", "-s", help="System prompt")
    
    # Generation options
    parser.add_argument("--no-stream", action="store_true", help="Disable streaming output")
    parser.add_argument("--temperature", "-t", type=float, default=0.7, help="Temperature (0.0-2.0)")
    
    return parser


def main():
    """Main entry point"""
    parser = create_parser()
    args = parser.parse_args()
    
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
