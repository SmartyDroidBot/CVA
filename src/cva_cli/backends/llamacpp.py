"""llama.cpp server backend implementation"""

import json
import requests
from typing import Iterator, List, Optional

from .base import LLMBackend, ModelInfo, GenerationConfig


class LlamaCppBackend(LLMBackend):
    """Backend implementation for llama.cpp server"""
    
    def __init__(self, model: str = "default", base_url: str = "http://localhost:8080", **kwargs):
        super().__init__(model, base_url, **kwargs)
    
    @property
    def backend_name(self) -> str:
        return "llama.cpp"
    
    def health_check(self) -> bool:
        """Check if llama.cpp server is available"""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        config: Optional[GenerationConfig] = None
    ) -> str:
        """Generate response using llama.cpp server"""
        if config and config.stream:
            return "".join(self.generate_stream(prompt, system, config))
        
        url = f"{self.base_url}/completion"
        payload = self._build_payload(prompt, system, config, stream=False)
        
        try:
            response = requests.post(url, json=payload, timeout=300)
            response.raise_for_status()
            data = response.json()
            return data.get("content", "")
        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"Cannot connect to llama.cpp server at {self.base_url}")
        except Exception as e:
            raise RuntimeError(f"Error generating response: {e}")
    
    def generate_stream(
        self,
        prompt: str,
        system: Optional[str] = None,
        config: Optional[GenerationConfig] = None
    ) -> Iterator[str]:
        """Generate streaming response"""
        url = f"{self.base_url}/completion"
        payload = self._build_payload(prompt, system, config, stream=True)
        
        try:
            response = requests.post(url, json=payload, stream=True, timeout=300)
            response.raise_for_status()
            
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith("data: "):
                        try:
                            data = json.loads(line_str[6:])
                            chunk = data.get("content", "")
                            if chunk:
                                yield chunk
                            if data.get("stop", False):
                                break
                        except json.JSONDecodeError:
                            continue
        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"Cannot connect to llama.cpp server at {self.base_url}")
        except Exception as e:
            raise RuntimeError(f"Error generating response: {e}")
    
    def chat(
        self,
        message: str,
        system: Optional[str] = None,
        config: Optional[GenerationConfig] = None
    ) -> str:
        """Chat with conversation history (simulated)"""
        # llama.cpp doesn't have native chat API, so we build the prompt
        full_prompt = self._build_chat_prompt(message, system)
        response = self.generate(full_prompt, config=config)
        
        # Add to history
        self.add_message("user", message)
        self.add_message("assistant", response)
        
        return response
    
    def chat_stream(
        self,
        message: str,
        system: Optional[str] = None,
        config: Optional[GenerationConfig] = None
    ) -> Iterator[str]:
        """Chat with streaming response"""
        full_prompt = self._build_chat_prompt(message, system)
        
        full_response = ""
        for chunk in self.generate_stream(full_prompt, config=config):
            full_response += chunk
            yield chunk
        
        # Add to history
        self.add_message("user", message)
        self.add_message("assistant", full_response)
    
    def list_models(self) -> List[ModelInfo]:
        """List models (llama.cpp typically runs one model)"""
        try:
            response = requests.get(f"{self.base_url}/props", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return [ModelInfo(
                    name=self.model,
                    description=f"llama.cpp model (context: {data.get('default_generation_settings', {}).get('n_ctx', 'unknown')})"
                )]
        except:
            pass
        
        return [ModelInfo(name=self.model, description="llama.cpp model")]
    
    def _build_payload(
        self,
        prompt: str,
        system: Optional[str],
        config: Optional[GenerationConfig],
        stream: bool
    ) -> dict:
        """Build payload for llama.cpp server"""
        # Prepend system prompt if provided
        if system:
            prompt = f"{system}\n\n{prompt}"
        
        payload = {
            "prompt": prompt,
            "stream": stream
        }
        
        if config:
            if config.temperature is not None:
                payload["temperature"] = config.temperature
            if config.top_p is not None:
                payload["top_p"] = config.top_p
            if config.top_k is not None:
                payload["top_k"] = config.top_k
            if config.max_tokens is not None:
                payload["n_predict"] = config.max_tokens
            if config.stop_sequences:
                payload["stop"] = config.stop_sequences
        
        return payload
    
    def _build_chat_prompt(self, message: str, system: Optional[str] = None) -> str:
        """Build a chat-style prompt from history"""
        lines = []
        
        if system:
            lines.append(f"System: {system}")
        
        for msg in self.conversation_history:
            if msg.role == "user":
                lines.append(f"User: {msg.content}")
            elif msg.role == "assistant":
                lines.append(f"Assistant: {msg.content}")
        
        lines.append(f"User: {message}")
        lines.append("Assistant:")
        
        return "\n\n".join(lines)
