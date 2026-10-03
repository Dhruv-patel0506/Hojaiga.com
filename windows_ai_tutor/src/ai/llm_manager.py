"""
LLM Manager - Local LLM Integration with Distributed Computing

This manages integration with local AI backends (Ollama or llama.cpp)
with automatic fallback to backup models and distributed GPU support.
Equivalent to ClaudeAPI in Clicky.
"""

import asyncio
import json
from typing import Optional, List, Tuple, Callable
from PyQt5.QtCore import QObject, pyqtSignal
import aiohttp
import base64
import requests

from ..utils.logger import setup_logger
from ..utils.config import ConfigManager


class LLMManager(QObject):
    """
    Manages integration with local AI backends (Ollama, llama.cpp, or distributed).
    Supports automatic fallback to backup models and distributed GPU selection.
    """

    # Signals
    response_chunk = pyqtSignal(str)  # Streaming response chunk
    response_complete = pyqtSignal(str)  # Complete response
    error_occurred = pyqtSignal(str)  # Error message
    node_switched = pyqtSignal(str)  # Node switch notification

    def __init__(self, config_manager: ConfigManager):
        """
        Initialize the LLM manager.

        Args:
            config_manager: Configuration manager instance
        """
        super().__init__()

        self.logger = setup_logger("LLMManager")
        self.config = config_manager

        # Backend configuration
        self.backend = self.config.get("backend", "llamacpp")  # 'ollama', 'llamacpp', or 'distributed'
        self.model = self.config.get("model", "Qwen2.5-VL-7B-Instruct")  # Primary model
        self.backup_model = self.config.get("backup_model", "llava-llama3")  # Backup model
        self.temperature = self.config.get("ai_temperature", 0.7)
        self.max_tokens = self.config.get("ai_max_tokens", 1024)

        # Debug: log what we actually got
        self.logger.info(f"Config read - backend: {self.backend}, model: {self.model}, backup: {self.backup_model}")
        self.logger.info(f"Full config keys: {list(self.config.config.keys())}")

        # Distributed computing configuration
        self.enable_distributed = self.config.get("enable_distributed", False)
        self.distributed_nodes = self.config.get("distributed_nodes", [])
        self.current_node: Optional[str] = None
        self.fallback_to_local = True

        # Ollama configuration
        self.ollama_host = self.config.get("ollama_host", "http://localhost:11434")

        # llama.cpp configuration
        self.llamacpp_host = self.config.get("llamacpp_host", "http://localhost:8081")
        self.llamacpp_model_path = self.config.get("llamacpp_model_path", "")
        self.llamacpp_mmproj_path = self.config.get("llamacpp_mmproj_path", "")
        self.llamacpp_binary_path = self.config.get("llamacpp_binary_path", "")

        # HTTP session
        self.session: Optional[aiohttp.ClientSession] = None

        self.logger.info(f"LLM manager initialized with {self.backend} backend")
        self.logger.info(f"Primary model: {self.model}, Backup: {self.backup_model}")

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=120)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session

    def _get_api_host(self) -> str:
        """Get the appropriate API host based on backend."""
        if self.backend == "distributed":
            return self._get_best_distributed_node()
        elif self.backend == "llamacpp":
            return self.llamacpp_host
        else:
            return self.ollama_host

    def _get_best_distributed_node(self) -> str:
        """
        Find the best available distributed node based on GPU availability.

        Returns:
            URL of the best node, or local fallback
        """
        if not self.enable_distributed or not self.distributed_nodes:
            self.logger.info("Distributed computing disabled, using local")
            return self.ollama_host

        best_node = None
        best_vram = 0

        for node in self.distributed_nodes:
            try:
                # Check node availability and VRAM
                vram = self._check_node_vram(node)
                if vram > best_vram:
                    best_vram = vram
                    best_node = node

            except Exception as e:
                self.logger.debug(f"Error checking node {node}: {e}")

    def _check_node_vram(self, node_url: str) -> int:
        """
        Check VRAM availability on a node (synchronous).

        Args:
            node_url: URL of the node to check

        Returns:
            Available VRAM in GB
        """
        try:
            import requests
            response = requests.get(f"{node_url}/health", timeout=2)
            if response.status_code == 200:
                data = response.json()
                vram = data.get("vram_available", 0)
                self.logger.info(f"Node {node_url}: {vram}GB VRAM available")
                return vram
        except:
            self.logger.debug(f"Node {node_url} not available")
        return 0

        if best_node and best_vram > 6:  # Only use if significantly better than local
            self.logger.info(f"Using distributed node: {best_node} ({best_vram}GB VRAM)")
            self.current_node = best_node
            self.node_switched.emit(best_node)
            return best_node
        else:
            self.logger.info("No better distributed node available, using local")
            self.current_node = None
            return self.ollama_host

    def generate_simple_response(self, user_message: str, images: Optional[List] = None) -> str:
        """
        Generate a simple response from the AI (synchronous wrapper).

        Args:
            user_message: User's message
            images: Optional list of image data (screenshots)

        Returns:
            AI response
        """
        try:
            # Default system prompt for vision tasks
            if images:
                system_prompt = """You are a helpful AI assistant with vision capabilities and drawing abilities.
When the user asks you to "draw" or create visual elements, you must provide DRAWING INSTRUCTIONS using coordinate tags, NOT text descriptions.

Use this exact format for coordinates: [POINT:x,y:label:screen0]
- x,y are pixel coordinates on the screen
- label is the name of the element
- screen0 indicates the primary screen

For drawing shapes:
- Circle: [POINT:960,540:center:screen0] [POINT:900,540:left:screen0] [POINT:1020,540:right:screen0]
- Rectangle: [POINT:500,300:top-left:screen0] [POINT:1420,300:top-right:screen0] [POINT:1420,780:bottom-right:screen0] [POINT:500,780:bottom-left:screen0]
- Lines: [POINT:x1,y1:start:screen0] [POINT:x2,y2:end:screen0]

Be concise and practical. Provide multiple coordinate points to define shapes clearly."""
            else:
                system_prompt = """You are a helpful AI assistant. Be concise and helpful.
When asked to draw or show something, provide screen coordinate instructions using [POINT:x,y:label:screen0] format."""

            # Run the async method in a simple way
            import requests
            import json

            api_host = self._get_api_host()
            url = f"{api_host}/v1/chat/completions"

            # Build messages
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]

            # Add images if present
            if images:
                import base64
                for image in images:
                    if isinstance(image, str):
                        image_base64 = image
                    elif hasattr(image, 'image_data'):
                        image_base64 = base64.b64encode(image.image_data).decode('utf-8')
                    else:
                        image_base64 = base64.b64encode(image).decode('utf-8')

                    # Modify user message to include image
                    messages[1]["content"] = [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        },
                        {
                            "type": "text",
                            "text": user_message
                        }
                    ]

            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 1024
            }

            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()

            data = response.json()
            result = data["choices"][0]["message"]["content"]
            self.logger.info(f"AI response: {result[:100]}..." if len(result) > 100 else f"AI response: {result}")
            return result
        except Exception as e:
            self.logger.error(f"Error generating simple response: {e}")
            return f"Error: {str(e)}"

    async def generate_response(
        self,
        system_prompt: str,
        user_prompt: str,
        images: Optional[List] = None,
        conversation_history: Optional[List[Tuple[str, str]]] = None,
        on_chunk: Optional[Callable] = None
    ) -> str:
        """
        Generate a response from the AI with automatic fallback to backup model.

        Args:
            system_prompt: System prompt for the AI
            user_prompt: User prompt
            images: List of screen captures (optional)
            conversation_history: Previous conversation turns
            on_chunk: Callback for streaming response chunks

        Returns:
            Complete AI response
        """
        try:
            return await self._generate_response_with_fallback(
                system_prompt, user_prompt, images, conversation_history, on_chunk
            )
        except Exception as e:
            self.logger.error(f"Error generating response: {e}")
            self.error_occurred.emit(f"LLM error: {str(e)}")
            raise

    async def _generate_response_with_fallback(
        self,
        system_prompt: str,
        user_prompt: str,
        images: Optional[List] = None,
        conversation_history: Optional[List[Tuple[str, str]]] = None,
        on_chunk: Optional[Callable] = None
    ) -> str:
        """Generate response with automatic fallback to backup model."""
        try:
            return await self._generate_response_internal(
                system_prompt, user_prompt, images, conversation_history, on_chunk
            )
        except Exception as e:
            self.logger.error(f"Error generating response with {self.model}: {e}")

            # Try fallback to backup model
            if self.model != self.backup_model:
                self.logger.info(f"Falling back to backup model: {self.backup_model}")
                try:
                    original_model = self.model
                    self.model = self.backup_model

                    fallback_response = await self._generate_response_internal(
                        system_prompt, user_prompt, images, conversation_history, on_chunk
                    )

                    self.model = original_model  # Restore original model
                    return fallback_response

                except Exception as fallback_error:
                    self.logger.error(f"Backup model also failed: {fallback_error}")
                    raise
            else:
                raise

    async def _generate_response_internal(
        self,
        system_prompt: str,
        user_prompt: str,
        images: Optional[List] = None,
        conversation_history: Optional[List[Tuple[str, str]]] = None,
        on_chunk: Optional[Callable] = None
    ) -> str:
        """Internal method for generating response."""
        try:
            session = await self._get_session()

            # Build messages array
            messages = []

            # Add system prompt
            messages.append({
                "role": "system",
                "content": system_prompt
            })

            # Add conversation history
            if conversation_history:
                for user_msg, assistant_msg in conversation_history:
                    messages.append({"role": "user", "content": user_msg})
                    messages.append({"role": "assistant", "content": assistant_msg})

            # Add current message with images
            if images:
                # Build content with images
                content = []

                # Add images
                for image in images:
                    import base64
                    # Handle both ScreenCapture objects and base64 strings
                    if hasattr(image, 'image_data'):
                        image_base64 = base64.b64encode(image.image_data).decode('utf-8')
                    elif isinstance(image, str):
                        # Already base64 string
                        image_base64 = image
                    else:
                        # Raw bytes
                        image_base64 = base64.b64encode(image).decode('utf-8')

                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        }
                    })

                # Add user prompt
                content.append({
                    "type": "text",
                    "text": user_prompt
                })

                messages.append({
                    "role": "user",
                    "content": content
                })
            else:
                messages.append({
                    "role": "user",
                    "content": user_prompt
                })

            # Build request payload based on backend
            if self.backend == "llamacpp":
                # llama.cpp uses different API format
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "stream": True,
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens
                }
            else:
                # Ollama format
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "stream": True,
                    "options": {
                        "temperature": self.temperature,
                        "num_predict": self.max_tokens
                    }
                }

            self.logger.info(f"Sending request to {self.backend} using {self.model}")

            # Make request to appropriate backend
            api_host = self._get_api_host()
            # Use correct endpoint for llama.cpp (OpenAI-compatible)
            if self.backend == "llamacpp":
                url = f"{api_host}/v1/chat/completions"
            else:
                url = f"{api_host}/api/chat"
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"API error {response.status}: {error_text}")

                # Stream response
                full_response = ""
                async for line in response.content:
                    if not line:
                        continue

                    try:
                        # Parse SSE format
                        line_str = line.decode('utf-8').strip()
                        if not line_str.startswith('data: '):
                            continue

                        json_str = line_str[6:]  # Remove 'data: ' prefix
                        if json_str == '[DONE]':
                            break

                        data = json.loads(json_str)

                        if 'message' in data and 'content' in data['message']:
                            chunk = data['message']['content']
                            full_response += chunk

                            # Emit chunk
                            self.response_chunk.emit(chunk)
                            if on_chunk:
                                on_chunk(chunk)

                    except json.JSONDecodeError:
                        continue

            self.logger.info(f"Received response: {len(full_response)} chars")
            self.response_complete.emit(full_response)

            return full_response

        except Exception as e:
            self.logger.error(f"Error in _generate_response_internal: {e}")
            raise

    async def check_connection(self) -> bool:
        """
        Check if the AI backend is running and accessible.

        Returns:
            True if backend is accessible
        """
        try:
            session = await self._get_session()
            api_host = self._get_api_host()
            url = f"{api_host}/api/tags"

            async with session.get(url) as response:
                return response.status == 200

        except Exception as e:
            self.logger.error(f"{self.backend} connection check failed: {e}")
            return False

    async def list_models(self) -> List[str]:
        """
        List available models in the current backend.

        Returns:
            List of model names
        """
        try:
            session = await self._get_session()
            api_host = self._get_api_host()
            url = f"{api_host}/api/tags"

            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    models = [model['name'] for model in data.get('models', [])]
                    self.logger.info(f"Available models: {models}")
                    return models
                else:
                    return []

        except Exception as e:
            self.logger.error(f"Error listing models: {e}")
            return []

    def set_model(self, model: str):
        """
        Set the AI model to use.

        Args:
            model: Model name (e.g., 'llama3', 'mistral', 'qwen2.5-vl')
        """
        self.model = model
        self.config.set("model", model)
        self.logger.info(f"Model changed to: {model}")

    def set_backup_model(self, model: str):
        """
        Set the backup AI model.

        Args:
            model: Backup model name
        """
        self.backup_model = model
        self.config.set("backup_model", model)
        self.logger.info(f"Backup model set to: {model}")

    def set_backend(self, backend: str):
        """
        Set the AI backend to use.

        Args:
            backend: Backend type ('ollama', 'llamacpp', or 'distributed')
        """
        self.backend = backend
        self.config.set("backend", backend)
        self.logger.info(f"Backend changed to: {backend}")

    def add_distributed_node(self, node_url: str):
        """
        Add a distributed computing node.

        Args:
            node_url: URL of the distributed node (e.g., 'http://192.168.1.100:11434')
        """
        if node_url not in self.distributed_nodes:
            self.distributed_nodes.append(node_url)
            self.config.set("distributed_nodes", self.distributed_nodes)
            self.logger.info(f"Added distributed node: {node_url}")

    def remove_distributed_node(self, node_url: str):
        """
        Remove a distributed computing node.

        Args:
            node_url: URL of the distributed node to remove
        """
        if node_url in self.distributed_nodes:
            self.distributed_nodes.remove(node_url)
            self.config.set("distributed_nodes", self.distributed_nodes)
            self.logger.info(f"Removed distributed node: {node_url}")

    def enable_distributed_computing(self, enabled: bool):
        """
        Enable or disable distributed computing.

        Args:
            enabled: Whether to enable distributed computing
        """
        self.enable_distributed = enabled
        self.config.set("enable_distributed", enabled)
        self.logger.info(f"Distributed computing: {enabled}")

    def cleanup(self):
        """Clean up resources."""
        if self.session and not self.session.closed:
            asyncio.create_task(self.session.close())
        self.logger.info("LLM manager cleaned up")