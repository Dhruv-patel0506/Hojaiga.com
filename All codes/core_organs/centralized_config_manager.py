"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: System-Level Coordinator
Name: Centralized Configuration Manager

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
```mermaid
graph TD
    classDef default fill:#1e1e1e;stroke:#333;stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d;stroke:#569cd6;stroke-width:2px,color:#d4d4d4;
    
    CONFIG[Configuration Manager]
    
    CONFIG --> STORE[Configuration Store]
    
    CONFIG --> VALIDATOR[Schema Validator]
    
    CONFIG --> WATCHER[File Watcher]
    
    CONFIG --> CACHE[In-Memory Cache]
    
    class CONFIG component
    class STORE component
    class VALIDATOR component
    class WATCHER component
    class CACHE component
```

Inputs: Configuration requests, environment variables
Outputs: Configuration values, validation results
Dependencies: typing, logging, json, os, threading...
"""

from __future__ import annotations

import logging
import json
import os
import threading
from typing import Dict, Any, Optional, List, Set, Union
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import time

logger = logging.getLogger("hojaiga.config_manager")


class ConfigSource(str, Enum):
    """Sources of configuration values."""
    DEFAULT = "default"
    ENV_VAR = "env_var"
    CONFIG_FILE = "config_file"
    OVERRIDE = "override"


class ConfigValueType(str, Enum):
    """Types of configuration values."""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    LIST = "list"
    DICT = "dict"


@dataclass
class ConfigSchema:
    """Schema definition for a configuration value."""
    key: str
    value_type: ConfigValueType
    default: Any
    description: str
    required: bool = False
    allowed_values: Optional[List[Any]] = None
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None
    env_var: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value_type": self.value_type.value,
            "default": self.default,
            "description": self.description,
            "required": self.required,
            "allowed_values": self.allowed_values,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "env_var": self.env_var
        }


@dataclass
class ConfigValue:
    """Represents a configuration value with metadata."""
    key: str
    value: Any
    source: ConfigSource
    schema: ConfigSchema
    last_modified: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "source": self.source.value,
            "schema": self.schema.to_dict(),
            "last_modified": self.last_modified
        }


class CentralizedConfigurationManager:
    """
    Centralized configuration manager that:
    - Provides single source of truth for all configuration
    - Supports multiple sources (defaults, env vars, config files)
    - Validates configuration against schemas
    - Watches for configuration file changes
    - Provides hot-reload capabilities
    - Prevents configuration drift across organs
    """
    
    def __init__(self, config_file: Optional[str] = None):
        self._config_file = config_file or "D:\\new_automation\\hojaiga_config.json"
        self._schemas: Dict[str, ConfigSchema] = {}
        self._values: Dict[str, ConfigValue] = {}
        self._lock = threading.RLock()
        self._watcher_thread: Optional[threading.Thread] = None
        self._running = False
        self._watch_interval = 5.0  # seconds
        self._last_file_mtime: float = 0.0
        
        # Initialize default schemas
        self._initialize_default_schemas()
        
        # Load configuration
        self._load_configuration()
        
        logger.info(f"[Config Manager] Initialized with config file: {self._config_file}")
    
    def _initialize_default_schemas(self) -> None:
        """Initialize default configuration schemas."""
        # LLM Gateway Configuration - primary reasoning model runs qwen2.5:7b locally
        self._schemas["HOJAIGA_BRAIN_MODEL"] = ConfigSchema(
            key="HOJAIGA_BRAIN_MODEL",
            value_type=ConfigValueType.STRING,
            default="qwen2.5:7b",
            description="Main brain model for task compilation (qwen2.5:7b for better intelligence)",
            env_var="HOJAIGA_BRAIN_MODEL"
        )
        
        self._schemas["HOJAIGA_SMALL_MODEL"] = ConfigSchema(
            key="HOJAIGA_SMALL_MODEL",
            value_type=ConfigValueType.STRING,
            default="qwen2.5:3b",
            description="Small text/vision model for routing and classification",
            env_var="HOJAIGA_SMALL_MODEL"
        )

        self._schemas["HOJAIGA_BRAIN_MODEL"] = ConfigSchema(
            key="HOJAIGA_BRAIN_MODEL",
            value_type=ConfigValueType.STRING,
            default="qwen2.5:7b",
            description="Core orchestrator & workflow compiler model (qwen2.5:7b for top-tier local reasoning)",
            env_var="HOJAIGA_BRAIN_MODEL"
        )

        self._schemas["HOJAIGA_VISION_MODEL"] = ConfigSchema(
            key="HOJAIGA_VISION_MODEL",
            value_type=ConfigValueType.STRING,
            default="llama3.2-vision:latest",
            description="Front-line vision & text handler model (llama3.2-vision for multimodal capabilities)",
            env_var="HOJAIGA_VISION_MODEL"
        )

        self._schemas["HOJAIGA_VISION_REASON_MODEL"] = ConfigSchema(
            key="HOJAIGA_VISION_REASON_MODEL",
            value_type=ConfigValueType.STRING,
            default="llama3.2-vision:latest",
            description="Vision-reasoning model for complex visual tasks",
            env_var="HOJAIGA_VISION_REASON_MODEL"
        )
        
        self._schemas["HOJAIGA_MODEL_DISTRIBUTION_ENABLED"] = ConfigSchema(
            key="HOJAIGA_MODEL_DISTRIBUTION_ENABLED",
            value_type=ConfigValueType.BOOLEAN,
            default=True,
            description="Enable distributed model processing when main model is heavy",
            env_var="HOJAIGA_MODEL_DISTRIBUTION_ENABLED"
        )
        
        self._schemas["HOJAIGA_MODEL_POOL_SIZE"] = ConfigSchema(
            key="HOJAIGA_MODEL_POOL_SIZE",
            value_type=ConfigValueType.INTEGER,
            default=3,
            description="Number of model instances in the processing pool",
            env_var="HOJAIGA_MODEL_POOL_SIZE",
            min_value=1,
            max_value=10
        )
        
        # Gatekeeper Configuration
        self._schemas["GATEKEEPER_PORT"] = ConfigSchema(
            key="GATEKEEPER_PORT",
            value_type=ConfigValueType.INTEGER,
            default=11435,
            description="Port for Gatekeeper service",
            env_var="GATEKEEPER_PORT",
            min_value=1024,
            max_value=65535
        )
        
        self._schemas["GATEKEEPER_PASSCODE"] = ConfigSchema(
            key="GATEKEEPER_PASSCODE",
            value_type=ConfigValueType.STRING,
            default="339680",
            description="Gatekeeper authentication passcode",
            env_var="GATEKEEPER_PASSCODE"
        )
        
        # Ollama Configuration
        self._schemas["OLLAMA_URL"] = ConfigSchema(
            key="OLLAMA_URL",
            value_type=ConfigValueType.STRING,
            default="http://127.0.0.1:11434",
            description="Ollama API endpoint",
            env_var="OLLAMA_URL"
        )
        
        # Vision Configuration
        self._schemas["VISION_MAX_LATENCY_MS"] = ConfigSchema(
            key="VISION_MAX_LATENCY_MS",
            value_type=ConfigValueType.INTEGER,
            default=10000,
            description="Maximum acceptable vision model latency in milliseconds",
            env_var="VISION_MAX_LATENCY_MS",
            min_value=1000,
            max_value=60000
        )
        
        self._schemas["VISION_PREWARM_MODELS"] = ConfigSchema(
            key="VISION_PREWARM_MODELS",
            value_type=ConfigValueType.LIST,
            default=["moondream", "qwen2.5vl:3b"],
            description="Vision models to pre-warm on startup",
            env_var="VISION_PREWARM_MODELS"
        )
        
        # Mouse Configuration
        self._schemas["MOUSE_MODE"] = ConfigSchema(
            key="MOUSE_MODE",
            value_type=ConfigValueType.STRING,
            default="advanced",
            description="Default mouse mode (clicky, advanced, drawing, stealth)",
            env_var="MOUSE_MODE",
            allowed_values=["clicky", "advanced", "drawing", "stealth"]
        )
        
        self._schemas["MOUSE_SMOOTH_MOVEMENT"] = ConfigSchema(
            key="MOUSE_SMOOTH_MOVEMENT",
            value_type=ConfigValueType.BOOLEAN,
            default=True,
            description="Enable smooth bezier curve mouse movement",
            env_var="MOUSE_SMOOTH_MOVEMENT"
        )
        
        # Task Compilation Configuration
        self._schemas["TASK_COMPILATION_CACHE_ENABLED"] = ConfigSchema(
            key="TASK_COMPILATION_CACHE_ENABLED",
            value_type=ConfigValueType.BOOLEAN,
            default=True,
            description="Enable task compilation caching",
            env_var="TASK_COMPILATION_CACHE_ENABLED"
        )
        
        self._schemas["TASK_COMPILATION_MAX_STEPS"] = ConfigSchema(
            key="TASK_COMPILATION_MAX_STEPS",
            value_type=ConfigValueType.INTEGER,
            default=50,
            description="Maximum number of steps in a compiled task",
            env_var="TASK_COMPILATION_MAX_STEPS",
            min_value=1,
            max_value=200
        )
        
        # Recovery Configuration
        self._schemas["RECOVERY_MAX_RETRIES"] = ConfigSchema(
            key="RECOVERY_MAX_RETRIES",
            value_type=ConfigValueType.INTEGER,
            default=3,
            description="Maximum number of recovery retries",
            env_var="RECOVERY_MAX_RETRIES",
            min_value=0,
            max_value=10
        )
        
        self._schemas["RECOVERY_BACKOFF_BASE"] = ConfigSchema(
            key="RECOVERY_BACKOFF_BASE",
            value_type=ConfigValueType.FLOAT,
            default=2.0,
            description="Base for exponential backoff in recovery",
            env_var="RECOVERY_BACKOFF_BASE",
            min_value=1.0,
            max_value=10.0
        )
        
        # Logging Configuration
        self._schemas["LOG_LEVEL"] = ConfigSchema(
            key="LOG_LEVEL",
            value_type=ConfigValueType.STRING,
            default="INFO",
            description="Global logging level",
            env_var="LOG_LEVEL",
            allowed_values=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        )
        
        logger.info(f"[Config Manager] Initialized {len(self._schemas)} default schemas")
    
    def register_schema(self, schema: ConfigSchema) -> None:
        """
        Register a new configuration schema.
        
        Args:
            schema: Configuration schema to register
        """
        with self._lock:
            self._schemas[schema.key] = schema
            logger.info(f"[Config Manager] Registered schema: {schema.key}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value.
        
        Args:
            key: Configuration key
            default: Default value if not found
        
        Returns:
            Configuration value
        """
        with self._lock:
            if key in self._values:
                return self._values[key].value
            
            # Check if schema exists
            if key in self._schemas:
                schema = self._schemas[key]
                return schema.default
            
            return default
    
    def set(self, key: str, value: Any, source: ConfigSource = ConfigSource.OVERRIDE) -> bool:
        """
        Set a configuration value.
        
        Args:
            key: Configuration key
            value: Value to set
            source: Source of the value
        
        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            # Get or create schema
            if key not in self._schemas:
                # Auto-create schema for unknown keys
                schema = ConfigSchema(
                    key=key,
                    value_type=self._infer_type(value),
                    default=value,
                    description="Auto-generated schema"
                )
                self._schemas[key] = schema
            else:
                schema = self._schemas[key]
            
            # Validate value
            if not self._validate_value(schema, value):
                logger.error(f"[Config Manager] Validation failed for {key}: {value}")
                return False
            
            # Set value
            self._values[key] = ConfigValue(
                key=key,
                value=value,
                source=source,
                schema=schema,
                last_modified=time.time()
            )
            
            logger.info(f"[Config Manager] Set {key} = {value} (source: {source.value})")
            
            return True
    
    def _infer_type(self, value: Any) -> ConfigValueType:
        """Infer the type of a value."""
        if isinstance(value, bool):
            return ConfigValueType.BOOLEAN
        elif isinstance(value, int):
            return ConfigValueType.INTEGER
        elif isinstance(value, float):
            return ConfigValueType.FLOAT
        elif isinstance(value, list):
            return ConfigValueType.LIST
        elif isinstance(value, dict):
            return ConfigValueType.DICT
        else:
            return ConfigValueType.STRING
    
    def _validate_value(self, schema: ConfigSchema, value: Any) -> bool:
        """Validate a value against its schema."""
        # Type check
        if schema.value_type == ConfigValueType.BOOLEAN and not isinstance(value, bool):
            return False
        elif schema.value_type == ConfigValueType.INTEGER and not isinstance(value, int):
            return False
        elif schema.value_type == ConfigValueType.FLOAT and not isinstance(value, (int, float)):
            return False
        elif schema.value_type == ConfigValueType.LIST and not isinstance(value, list):
            return False
        elif schema.value_type == ConfigValueType.DICT and not isinstance(value, dict):
            return False
        
        # Allowed values check
        if schema.allowed_values and value not in schema.allowed_values:
            return False
        
        # Range check
        if schema.min_value is not None and value < schema.min_value:
            return False
        if schema.max_value is not None and value > schema.max_value:
            return False
        
        return True
    
    def _load_configuration(self) -> None:
        """Load configuration from all sources in priority order."""
        with self._lock:
            # 1. Load defaults from schemas
            for key, schema in self._schemas.items():
                self._values[key] = ConfigValue(
                    key=key,
                    value=schema.default,
                    source=ConfigSource.DEFAULT,
                    schema=schema,
                    last_modified=time.time()
                )
            
            # 2. Load from environment variables
            for key, schema in self._schemas.items():
                if schema.env_var and schema.env_var in os.environ:
                    env_value = os.environ[schema.env_var]
                    try:
                        parsed_value = self._parse_value(env_value, schema.value_type)
                        if self._validate_value(schema, parsed_value):
                            self._values[key] = ConfigValue(
                                key=key,
                                value=parsed_value,
                                source=ConfigSource.ENV_VAR,
                                schema=schema,
                                last_modified=time.time()
                            )
                            logger.info(f"[Config Manager] Loaded {key} from env var: {schema.env_var}")
                    except Exception as e:
                        logger.warning(f"[Config Manager] Failed to parse env var {schema.env_var}: {e}")
            
            # 3. Load from config file
            if os.path.exists(self._config_file):
                try:
                    with open(self._config_file, 'r') as f:
                        file_config = json.load(f)
                    
                    for key, value in file_config.items():
                        if key in self._schemas:
                            schema = self._schemas[key]
                            if self._validate_value(schema, value):
                                self._values[key] = ConfigValue(
                                    key=key,
                                    value=value,
                                    source=ConfigSource.CONFIG_FILE,
                                    schema=schema,
                                    last_modified=time.time()
                                )
                                logger.info(f"[Config Manager] Loaded {key} from config file")
                    
                    self._last_file_mtime = os.path.getmtime(self._config_file)
                    
                except Exception as e:
                    logger.error(f"[Config Manager] Failed to load config file: {e}")
    
    def _parse_value(self, value: str, value_type: ConfigValueType) -> Any:
        """Parse a string value to the correct type."""
        if value_type == ConfigValueType.BOOLEAN:
            return value.lower() in ('true', '1', 'yes', 'on')
        elif value_type == ConfigValueType.INTEGER:
            return int(value)
        elif value_type == ConfigValueType.FLOAT:
            return float(value)
        elif value_type == ConfigValueType.LIST:
            return json.loads(value)
        elif value_type == ConfigValueType.DICT:
            return json.loads(value)
        else:
            return value
    
    def save_configuration(self) -> bool:
        """Save current configuration to file."""
        with self._lock:
            try:
                config_to_save = {}
                for key, config_value in self._values.items():
                    if config_value.source in [ConfigSource.CONFIG_FILE, ConfigSource.OVERRIDE]:
                        config_to_save[key] = config_value.value
                
                with open(self._config_file, 'w') as f:
                    json.dump(config_to_save, f, indent=2)
                
                self._last_file_mtime = os.path.getmtime(self._config_file)
                logger.info(f"[Config Manager] Saved configuration to {self._config_file}")
                return True
                
            except Exception as e:
                logger.error(f"[Config Manager] Failed to save configuration: {e}")
                return False
    
    def start_watcher(self) -> None:
        """Start the configuration file watcher."""
        if self._running:
            logger.info("[Config Manager] Watcher already running")
            return
        
        self._running = True
        self._watcher_thread = threading.Thread(target=self._watcher_loop, daemon=True, name="config-watcher")
        self._watcher_thread.start()
        logger.info("[Config Manager] Configuration watcher started")
    
    def stop_watcher(self) -> None:
        """Stop the configuration file watcher."""
        self._running = False
        if self._watcher_thread:
            self._watcher_thread.join(timeout=5.0)
        logger.info("[Config Manager] Configuration watcher stopped")
    
    def _watcher_loop(self) -> None:
        """Background watcher loop for configuration file changes."""
        logger.info("[Config Manager] Watcher loop started")
        
        while self._running:
            try:
                time.sleep(self._watch_interval)
                
                # Check if file has been modified
                if os.path.exists(self._config_file):
                    current_mtime = os.path.getmtime(self._config_file)
                    if current_mtime > self._last_file_mtime:
                        logger.info("[Config Manager] Configuration file modified, reloading...")
                        self._load_configuration()
                        self._last_file_mtime = current_mtime
                
            except Exception as e:
                logger.error(f"[Config Manager] Watcher loop error: {e}")
        
        logger.info("[Config Manager] Watcher loop stopped")
    
    def get_all_values(self) -> Dict[str, Dict[str, Any]]:
        """Get all configuration values with metadata."""
        with self._lock:
            return {
                key: config_value.to_dict()
                for key, config_value in self._values.items()
            }
    
    def get_schema(self, key: str) -> Optional[ConfigSchema]:
        """Get the schema for a configuration key."""
        return self._schemas.get(key)
    
    def get_all_schemas(self) -> Dict[str, Dict[str, Any]]:
        """Get all configuration schemas."""
        with self._lock:
            return {
                key: schema.to_dict()
                for key, schema in self._schemas.items()
            }
    
    def export_config(self, file_path: str) -> bool:
        """Export current configuration to a file."""
        with self._lock:
            try:
                config_export = {
                    key: config_value.value
                    for key, config_value in self._values.items()
                }
                
                with open(file_path, 'w') as f:
                    json.dump(config_export, f, indent=2)
                
                logger.info(f"[Config Manager] Exported configuration to {file_path}")
                return True
                
            except Exception as e:
                logger.error(f"[Config Manager] Failed to export configuration: {e}")
                return False


# Singleton instance
_config_manager_instance: Optional[CentralizedConfigurationManager] = None

def get_config_manager() -> CentralizedConfigurationManager:
    """Get the singleton configuration manager instance."""
    global _config_manager_instance
    if _config_manager_instance is None:
        _config_manager_instance = CentralizedConfigurationManager()
    return _config_manager_instance


def get_config(key: str, default: Any = None) -> Any:
    """
    Convenience function to get a configuration value.
    
    Args:
        key: Configuration key
        default: Default value if not found
    
    Returns:
        Configuration value
    """
    manager = get_config_manager()
    return manager.get(key, default)


def set_config(key: str, value: Any) -> bool:
    """
    Convenience function to set a configuration value.
    
    Args:
        key: Configuration key
        value: Value to set
    
    Returns:
        True if successful, False otherwise
    """
    manager = get_config_manager()
    return manager.set(key, value)
