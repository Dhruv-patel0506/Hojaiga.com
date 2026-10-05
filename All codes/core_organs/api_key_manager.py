"""
API Key Manager for Hojaiga

Manages default API keys (free) and user-provided API keys (free or paid).
Cost responsibility is on the key provider.
Uses secure SHA-256 hashing for key storage.
"""

import json
import os
from typing import Optional, Dict, Any
from pathlib import Path
import logging

logger = logging.getLogger("hojaiga.api_key_manager")

# Import secure storage
try:
    from core_organs.secure_key_storage import get_secure_storage
    SECURE_STORAGE_AVAILABLE = True
except ImportError:
    SECURE_STORAGE_AVAILABLE = False
    logger.warning("[APIKeyManager] Secure storage not available, using fallback")


class APIKeyManager:
    """Manages API keys for various services."""
    
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = r"D:\new_automation\config\api_keys.json"
        
        self.config_path = Path(config_path)
        self.config = self._load_config()
        
        # Initialize secure storage
        if SECURE_STORAGE_AVAILABLE:
            self.secure_storage = get_secure_storage()
        else:
            self.secure_storage = None
    
    def _load_config(self) -> Dict[str, Any]:
        """Load API key configuration."""
        if not self.config_path.exists():
            self.config_path.parent.mkdir(exist_ok=True)
            default_config = {
                "default_keys": {},
                "user_keys": {}
            }
            with open(self.config_path, 'w') as f:
                json.dump(default_config, f, indent=2)
            logger.info(f"[APIKeyManager] Created default config at {self.config_path}")
            return default_config
        
        with open(self.config_path, 'r') as f:
            return json.load(f)
    
    def _save_config(self):
        """Save API key configuration."""
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def get_key(self, service: str, use_user_key: bool = False) -> Optional[str]:
        """
        Get API key for a service.
        
        Args:
            service: Service name (discord, telegram, github, etc.)
            use_user_key: Whether to use user-provided key (if available)
        
        Returns:
            API key or None
        """
        # Try secure storage first
        if self.secure_storage:
            key = self.secure_storage.get_key(service)
            if key:
                logger.info(f"[APIKeyManager] Retrieved key from secure storage for {service}")
                return key
        
        # Try user key from config
        if use_user_key and service in self.config.get("user_keys", {}):
            user_key_config = self.config["user_keys"][service]
            if user_key_config.get("enabled", False):
                key = user_key_config.get("api_key") or user_key_config.get("bot_token") or user_key_config.get("access_token")
                if key:
                    logger.info(f"[APIKeyManager] Using user-provided key for {service} (provided by: {user_key_config.get('provided_by', 'unknown')})")
                    return key
        
        # Fall back to default key from config
        if service in self.config.get("default_keys", {}):
            default_key = self.config["default_keys"][service]
            # Handle different key formats
            if isinstance(default_key, dict):
                key = default_key.get("bot_token") or default_key.get("api_key") or default_key.get("access_token") or default_key.get("key")
            else:
                key = default_key
            
            if key and not key.startswith("YOUR_"):
                logger.info(f"[APIKeyManager] Using default key for {service}")
                return key
            else:
                logger.warning(f"[APIKeyManager] Default key for {service} not configured (placeholder value)")
        
        logger.warning(f"[APIKeyManager] No key found for {service}")
        return None
    
    def set_user_key(self, service: str, key: str, provided_by: str = "user", use_secure_storage: bool = True):
        """
        Set a user-provided API key.
        
        Args:
            service: Service name
            key: API key
            provided_by: Who provided the key (user identifier)
            use_secure_storage: Whether to use secure SHA-256 hashing
        """
        # Store in secure storage if available
        if use_secure_storage and self.secure_storage:
            self.secure_storage.store_key(service, key, encrypted=True)
            logger.info(f"[APIKeyManager] Key stored in secure storage for {service}")
        
        # Also store in config for metadata
        if "user_keys" not in self.config:
            self.config["user_keys"] = {}
        
        self.config["user_keys"][service] = {
            "enabled": True,
            "provided_by": provided_by,
            "stored_securely": use_secure_storage
        }
        
        self._save_config()
        logger.info(f"[APIKeyManager] User key metadata set for {service} by {provided_by}")
    
    def remove_user_key(self, service: str):
        """Remove a user-provided API key."""
        # Remove from secure storage
        if self.secure_storage:
            self.secure_storage.remove_key(service)
        
        # Remove from config
        if "user_keys" in self.config and service in self.config["user_keys"]:
            del self.config["user_keys"][service]
            self._save_config()
            logger.info(f"[APIKeyManager] User key removed for {service}")
    
    def get_key_info(self, service: str) -> Dict[str, Any]:
        """Get information about API key for a service."""
        info = {
            "service": service,
            "has_default_key": service in self.config.get("default_keys", {}),
            "has_user_key": service in self.config.get("user_keys", {}),
            "user_key_enabled": False,
            "stored_securely": False
        }
        
        if info["has_user_key"]:
            info["user_key_enabled"] = self.config["user_keys"][service].get("enabled", False)
            info["provided_by"] = self.config["user_keys"][service].get("provided_by", "unknown")
            info["stored_securely"] = self.config["user_keys"][service].get("stored_securely", False)
        
        if self.secure_storage:
            info["secure_storage_available"] = True
            services = self.secure_storage.list_services()
            info["has_secure_key"] = service in services
        else:
            info["secure_storage_available"] = False
            info["has_secure_key"] = False
        
        return info
    
    def list_all_services(self) -> Dict[str, Dict[str, Any]]:
        """List all services and their key status."""
        services = {}
        
        # Default keys
        for service in self.config.get("default_keys", {}).keys():
            services[service] = {
                "type": "default",
                "free": self._is_service_free(service),
                "configured": not self.config["default_keys"][service].get("bot_token", "YOUR_").startswith("YOUR_")
            }
        
        # User keys
        for service in self.config.get("user_keys", {}).keys():
            if service not in services:
                services[service] = {
                    "type": "user",
                    "free": self._is_service_free(service),
                    "enabled": self.config["user_keys"][service].get("enabled", False)
                }
        
        return services
    
    def _is_service_free(self, service: str) -> bool:
        """Check if a service has a free tier."""
        free_services = ["discord", "telegram", "github", "trello"]
        return service.lower() in free_services


# Singleton instance
_api_key_manager = None


def get_api_key_manager() -> APIKeyManager:
    """Get the singleton API key manager instance."""
    global _api_key_manager
    if _api_key_manager is None:
        _api_key_manager = APIKeyManager()
    return _api_key_manager
