"""Ollama backend implementation"""

import json
import requests
from typing import Iterator, List, Optional

from .base import LLMBackend, ModelInfo, GenerationConfig, GenerationResponse, Message


class OllamaBackend(LLMBackend):
    """Backend implementation for Ollama"""
    
    def __init__(self, model: str = "qwen3:8b", base_url: str = "http://localhost:11434", **kwargs):
        super().__init__(model, base_url, **kwargs)
    
    @property
    def backend_name(self) -> str:
        return "ollama"
    
    def health_check(self) -> bool:
        """Check if Ollama is available"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        config: Optional[GenerationConfig] = None
    ) -> str:
        """Generate response using Ollama API"""
        if config and config.stream:
            # Collect all chunks
            return "".join(self.generate_stream(prompt, system, config))
        
        url = f"{self.base_url}/api/generate"
        payload = self._build_generate_payload(prompt, system, config, stream=False)
        
        try:
            response = requests.post(url, json=payload, timeout=300)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"Cannot connect to Ollama at {self.base_url}. Is Ollama running?")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise RuntimeError(
                    f"Model '{self.model}' not found. "
                    f"Available models: {', '.join([m.name for m in self.list_models()])}. "
                    f"Pull a model with: ollama pull {self.model}"
                )
            raise RuntimeError(f"Failed to list models: {e}")
    
    def generate(
        self,
        model: str,
        messages: List[Message],
        config: Optional[GenerationConfig] = None
    ) -> GenerationResponse:
        """Generate response using Ollama chat API"""
        if config is None:
            config = GenerationConfig()
        
        url = f"{self.base_url}/api/chat"
        
        # Convert messages to format expected by Ollama
        formatted_messages = [{"role": msg.role, "content": msg.content} for msg in messages]
        
        payload = {
            "model": model,
            "messages": formatted_messages,
            "stream": False,
            "options": {
                "temperature": config.temperature
            }
        }
        
        if config.max_tokens:
            payload["options"]["num_predict"] = config.max_tokens
        
        try:
            response = requests.post(url, json=payload, timeout=config.timeout)
            response.raise_for_status()
            data = response.json()
            
            # Extract response content
            message_content = data.get("message", {}).get("content", "")
            
            # Extract usage information if available
            usage = None
            if "eval_count" in data:
                usage = {
                    "prompt_tokens": data.get("prompt_eval_count", 0),
                    "completion_tokens": data.get("eval_count", 0),
                    "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0)
                }
            
            return GenerationResponse(
                content=message_content,
                model=model,
                usage=usage,
                finish_reason=data.get("done_reason", "stop")
            )
        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"Cannot connect to Ollama at {self.base_url}. Is Ollama running?")
        except Exception as e:
            raise RuntimeError(f"Error generating response: {e}")
    
    def generate_stream(
        self,
        prompt: str,
        system: Optional[str] = None,
        config: Optional[GenerationConfig] = None
    ) -> Iterator[str]:
        """Generate streaming response using Ollama API"""
        url = f"{self.base_url}/api/generate"
        payload = self._build_generate_payload(prompt, system, config, stream=True)
        
        try:
            response = requests.post(url, json=payload, stream=True, timeout=300)
            response.raise_for_status()
            
            for line in response.iter_lines():
                if line:
                    data = json.loads(line)
                    chunk = data.get("response", "")
                    if chunk:
                        yield chunk
                    if data.get("done", False):
                        break
        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"Cannot connect to Ollama at {self.base_url}. Is Ollama running?")
        except Exception as e:
            raise RuntimeError(f"Error generating response: {e}")
    
    def chat(
        self,
        message: str,
        system: Optional[str] = None,
        config: Optional[GenerationConfig] = None
    ) -> str:
        """Send chat message using Ollama API"""
        if config and config.stream:
            # Collect all chunks
            return "".join(self.chat_stream(message, system, config))
        
        url = f"{self.base_url}/api/chat"
        
        # Add user message to history
        self.add_message("user", message)
        
        payload = self._build_chat_payload(system, config, stream=False)
        
        try:
            response = requests.post(url, json=payload, timeout=300)
            response.raise_for_status()
            data = response.json()
            response_text = data.get("message", {}).get("content", "")
            
            # Add assistant response to history
            self.add_message("assistant", response_text)
            
            return response_text
        except Exception as e:
            # Remove user message if request failed
            if self.conversation_history and self.conversation_history[-1].role == "user":
                self.conversation_history.pop()
            raise RuntimeError(f"Error in chat: {e}")
    
    def chat_stream(
        self,
        message: str,
        system: Optional[str] = None,
        config: Optional[GenerationConfig] = None
    ) -> Iterator[str]:
        """Send chat message with streaming response"""
        url = f"{self.base_url}/api/chat"
        
        # Add user message to history
        self.add_message("user", message)
        
        payload = self._build_chat_payload(system, config, stream=True)
        
        try:
            response = requests.post(url, json=payload, stream=True, timeout=300)
            response.raise_for_status()
            
            full_response = ""
            for line in response.iter_lines():
                if line:
                    data = json.loads(line)
                    chunk = data.get("message", {}).get("content", "")
                    if chunk:
                        full_response += chunk
                        yield chunk
                    if data.get("done", False):
                        break
            
            # Add complete assistant response to history
            self.add_message("assistant", full_response)
            
        except Exception as e:
            # Remove user message if request failed
            if self.conversation_history and self.conversation_history[-1].role == "user":
                self.conversation_history.pop()
            raise RuntimeError(f"Error in chat: {e}")
    
    def list_models(self) -> List[ModelInfo]:
        """List available Ollama models"""
        url = f"{self.base_url}/api/tags"
        
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()
            
            models = []
            for model_data in data.get("models", []):
                models.append(ModelInfo(
                    name=model_data.get("name", "unknown"),
                    size=model_data.get("size"),
                    description=model_data.get("details", {}).get("family"),
                    modified=model_data.get("modified_at")
                ))
            
            return models
        except Exception as e:
            raise RuntimeError(f"Error listing models: {e}")
    
    def _build_generate_payload(
        self,
        prompt: str,
        system: Optional[str],
        config: Optional[GenerationConfig],
        stream: bool
    ) -> dict:
        """Build payload for generate endpoint"""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": stream
        }
        
        if system:
            payload["system"] = system
        
        if config:
            options = {}
            if config.temperature is not None:
                options["temperature"] = config.temperature
            if config.top_p is not None:
                options["top_p"] = config.top_p
            if config.top_k is not None:
                options["top_k"] = config.top_k
            if options:
                payload["options"] = options
            
            if config.stop_sequences:
                payload["stop"] = config.stop_sequences
        
        return payload
    
    def _build_chat_payload(
        self,
        system: Optional[str],
        config: Optional[GenerationConfig],
        stream: bool
    ) -> dict:
        """Build payload for chat endpoint"""
        # Convert internal Message objects to API format
        messages = [
            {"role": msg.role, "content": msg.content}
            for msg in self.conversation_history
        ]
        
        # Add system message if provided
        if system and (not messages or messages[0]["role"] != "system"):
            messages.insert(0, {"role": "system", "content": system})
        
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream
        }
        
        if config:
            options = {}
            if config.temperature is not None:
                options["temperature"] = config.temperature
            if config.top_p is not None:
                options["top_p"] = config.top_p
            if config.top_k is not None:
                options["top_k"] = config.top_k
            if options:
                payload["options"] = options
            
            if config.stop_sequences:
                payload["stop"] = config.stop_sequences
        
        return payload
