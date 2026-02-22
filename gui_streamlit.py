import streamlit as st
import subprocess
import json
import os
import yaml
from pathlib import Path

# Page config
st.set_page_config(
    page_title="Local LLM GUI",
    page_icon="🤖",
    layout="wide"
)

# Load configuration
@st.cache_data
def load_config():
    config_path = Path("config/config.yaml")
    agents_path = Path("config/agents.yaml")
    mcp_path = Path("config/mcp_servers.yaml")
    
    config = {}
    if config_path.exists():
        with open(config_path) as f:
            config['main'] = yaml.safe_load(f)
    if agents_path.exists():
        with open(agents_path) as f:
            config['agents'] = yaml.safe_load(f)
    if mcp_path.exists():
        with open(mcp_path) as f:
            config['mcp'] = yaml.safe_load(f)
    return config

# Get available models
@st.cache_data(ttl=60)
def get_models():
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True
        )
        lines = result.stdout.strip().split('\n')[1:]  # Skip header
        models = []
        for line in lines:
            if line.strip():
                model_name = line.split()[0]
                models.append(model_name)
        return models
    except:
        return ["Error: Ollama not running"]

# Main UI
st.title("🤖 Local LLM GUI")
st.markdown("Interact with your local LLM using Ollama")

# Sidebar for configuration
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # Model selection
    models = get_models()
    selected_model = st.selectbox("Select Model", models)
    
    # Load config
    config = load_config()
    
    # Agent selection
    if config.get('agents'):
        agents = list(config['agents'].keys())
        selected_agent = st.selectbox("Select Agent", ["None"] + agents)
    
    # Temperature
    temperature = st.slider("Temperature", 0.0, 2.0, 0.7, 0.1)
    
    # Max tokens
    max_tokens = st.number_input("Max Tokens", 100, 4096, 2048, 100)
    
    st.divider()
    
    # MCP Tools section
    st.header("🛠️ MCP Tools")
    if config.get('mcp'):
        for tool_name, tool_config in config['mcp'].items():
            enabled = st.checkbox(
                f"Enable {tool_name}",
                value=tool_config.get('enabled', False)
            )
            # Store in session state
            st.session_state[f"tool_{tool_name}"] = enabled

# Main chat area
col1, col2 = st.columns([3, 1])

with col1:
    # Chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # Chat input
    if prompt := st.chat_input("Type your message here..."):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Get assistant response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                # Build command
                cmd = ["python", "cva_cli.py"]
                if selected_model:
                    cmd.extend(["--model", selected_model])
                if selected_agent and selected_agent != "None":
                    cmd.extend(["--agent", selected_agent])
                
                # Add tool flags
                for tool_name in config.get('mcp', {}):
                    if st.session_state.get(f"tool_{tool_name}"):
                        cmd.extend(["--use-tool", tool_name])
                
                cmd.append(prompt)
                
                # Run command
                result = subprocess.run(cmd, capture_output=True, text=True)
                response = result.stdout or result.stderr
                
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})

with col2:
    st.header("📋 Available Actions")
    
    # Quick action buttons
    if st.button("📁 List Files", use_container_width=True):
        with st.spinner("Running..."):
            result = subprocess.run(
                ["python", "cva_cli.py", "--use-tool", "list_directory", 
                 "--tool-params", "path=."],
                capture_output=True, text=True
            )
            st.info(result.stdout or result.stderr)
    
    if st.button("🧮 Calculate", use_container_width=True):
        with st.spinner("Running..."):
            expr = st.text_input("Enter expression:", "2+2")
            if expr:
                result = subprocess.run(
                    ["python", "cva_cli.py", "--use-tool", "calculator",
                     "--tool-params", f"expression={expr}"],
                    capture_output=True, text=True
                )
                st.info(result.stdout or result.stderr)
    
    if st.button("🔄 Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()
    
    if st.button("📊 System Info", use_container_width=True):
        result = subprocess.run(
            ["python", "cva_cli.py", "--use-tool", "system_info"],
            capture_output=True, text=True
        )
        st.info(result.stdout or result.stderr)

# Status bar
st.divider()
col1, col2, col3 = st.columns(3)
with col1:
    st.success(f"✅ Using model: {selected_model}")
with col2:
    st.info(f"🤖 Agent: {selected_agent if selected_agent != 'None' else 'Default'}")
with col3:
    enabled_tools = [t for t in config.get('mcp', {}) 
                    if st.session_state.get(f"tool_{t}")]
    st.warning(f"🛠️ Tools: {', '.join(enabled_tools) if enabled_tools else 'None'}")
    