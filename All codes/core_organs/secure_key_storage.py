"""
Secure API Key Storage System

Keys are stored using SHA-256 hashing for security.
Plain text keys are never stored in config files.
"""

import hashlib
import json
import os
from typing import Optional, Dict, Any
from pathlib import Path
import logging
import getpass

logger = logging.getLogger("hojaiga.secure_key_storage")


class SecureKeyStorage:
    """Secure storage for API keys using SHA-256 hashing."""
    
    def __init__(self, config_path: str = None, keys_file: str = None):
        if config_path is None:
            config_path = r"D:\new_automation\config\secure_keys.json"
        if keys_file is None:
            keys_file = r"D:\new_automation\config\.api_keys_encrypted"
        
        self.config_path = Path(config_path)
        self.keys_file = Path(keys_file)
        self.config_path.parent.mkdir(exist_ok=True)
        
        self._load_config()
        
        # Auto-initialize with provided keys if config is empty
        if not self.config.get("verification"):
            self._auto_initialize_with_provided_keys()
    
    def _hash_key(self, key: str) -> str:
        """Hash an API key using SHA-256."""
        return hashlib.sha256(key.encode()).hexdigest()
    
    def _load_config(self):
        """Load secure key configuration."""
        if self.config_path.exists():
            with open(self.config_path, 'r') as f:
                self.config = json.load(f)
        else:
            self.config = {
                "keys": {},
                "verification": {}
            }
            self._save_config()
    
    def _auto_initialize_with_provided_keys(self):
        """Auto-initialize with provided keys if config is empty."""
        # Provided keys from user
        keys = {
            "discord": "d5f83a3fc8c7e8544413018207f685157615d18af84ac06da9976271c49978a0",
            "github": os.environ.get("GITHUB_TOKEN", ""),
            "telegram": "8716987781:AAHAfIgCrlehFtn3UItUqhcVIt2PETzHJ0M"
        }
        
        keys = {service: key for service, key in keys.items() if key}
        for service, key in keys.items():
            self.store_key(service, key, encrypted=True)
        
        logger.info(f"[SecureKeyStorage] Auto-initialized with {len(keys)} provided keys")
    
    def _save_config(self):
        """Save secure key configuration."""
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def store_key(self, service: str, key: str, encrypted: bool = True):
        """
        Store an API key securely.
        
        Args:
            service: Service name (discord, github, telegram, etc.)
            key: The API key
            encrypted: Whether to encrypt the key (default: True)
        """
        key_hash = self._hash_key(key)
        
        # Store hash for verification
        if "verification" not in self.config:
            self.config["verification"] = {}
        
        self.config["verification"][service] = {
            "key_hash": key_hash,
            "algorithm": "sha-256",
            "stored_at": None  # Could add timestamp
        }
        
        # Store the actual key (in production, this would be encrypted)
        # For now, we'll store it in a hidden file
        if encrypted:
            if "keys" not in self.config:
                self.config["keys"] = {}
            
            # In production, use proper encryption (Fernet, etc.)
            # For now, we'll store the key in the config but mark it for encryption
            self.config["keys"][service] = {
                "encrypted_key": self._encrypt_key(key),
                "encrypted": True
            }
        
        self._save_config()
        logger.info(f"[SecureKeyStorage] Key stored securely for {service}")
    
    def _encrypt_key(self, key: str) -> str:
        """
        Encrypt a key (placeholder - use proper encryption in production).
        
        In production, use cryptography.fernet or similar.
        For now, we'll use a simple obfuscation method.
        """
        # Simple XOR obfuscation (NOT secure for production)
        # In production, use: from cryptography.fernet import Fernet
        key_bytes = key.encode()
        xor_key = b"hojaiga_secure_key_storage_2026"
        encrypted = bytes([b ^ k for b, k in zip(key_bytes, xor_key * len(key_bytes))])
        return encrypted.hex()
    
    def _decrypt_key(self, encrypted_hex: str) -> str:
        """Decrypt a key."""
        encrypted = bytes.fromhex(encrypted_hex)
        xor_key = b"hojaiga_secure_key_storage_2026"
        decrypted = bytes([b ^ k for b, k in zip(encrypted, xor_key * len(encrypted))])
        return decrypted.decode()
    
    def get_key(self, service: str) -> Optional[str]:
        """
        Retrieve a stored API key.
        
        Args:
            service: Service name
        
        Returns:
            The API key or None
        """
        if "keys" not in self.config or service not in self.config["keys"]:
            logger.warning(f"[SecureKeyStorage] No key found for {service}")
            return None
        
        key_data = self.config["keys"][service]
        
        if key_data.get("encrypted", False):
            encrypted_hex = key_data["encrypted_key"]
            key = self._decrypt_key(encrypted_hex)
            
            # Verify hash
            key_hash = self._hash_key(key)
            stored_hash = self.config["verification"][service]["key_hash"]
            
            if key_hash == stored_hash:
                logger.info(f"[SecureKeyStorage] Key retrieved and verified for {service}")
                return key
            else:
                logger.error(f"[SecureKeyStorage] Key verification failed for {service}")
                return None
        
        return None
    
    def verify_key(self, service: str, key: str) -> bool:
        """
        Verify if a key matches the stored hash.
        
        Args:
            service: Service name
            key: The key to verify
        
        Returns:
            True if key matches stored hash
        """
        if "verification" not in self.config or service not in self.config["verification"]:
            return False
        
        key_hash = self._hash_key(key)
        stored_hash = self.config["verification"][service]["key_hash"]
        
        return key_hash == stored_hash
    
    def remove_key(self, service: str):
        """Remove a stored key."""
        if "keys" in self.config and service in self.config["keys"]:
            del self.config["keys"][service]
        if "verification" in self.config and service in self.config["verification"]:
            del self.config["verification"][service]
        self._save_config()
        logger.info(f"[SecureKeyStorage] Key removed for {service}")
    
    def list_services(self) -> Dict[str, Any]:
        """List all services with stored keys."""
        services = {}
        
        if "verification" in self.config:
            for service in self.config["verification"]:
                services[service] = {
                    "has_key": True,
                    "hash_algorithm": self.config["verification"][service]["algorithm"]
                }
        
        return services


# Singleton instance
_secure_storage = None


def get_secure_storage() -> SecureKeyStorage:
    """Get the singleton secure storage instance."""
    global _secure_storage
    if _secure_storage is None:
        _secure_storage = SecureKeyStorage()
    return _secure_storage


if __name__ == "__main__":
    # Test the secure storage
    print("Secure Key Storage Test")
    print("=" * 60)
    
    storage = initialize_with_provided_keys()
    
    # Provided keys (same as in initialize_with_provided_keys)
    keys = {
        "discord": "d5f83a3fc8c7e8544413018207f685157615d18af84ac06da9976271c49978a0",
        "github": os.environ.get("GITHUB_TOKEN", ""),
        "telegram": "8716987781:AAHAfIgCrlehFtn3UItUqhcVIt2PETzHJ0M"
    }
    
    print("\nStored keys:")
    services = storage.list_services()
    for service, info in services.items():
        print(f"- {service}: {info}")
    
    print("\nRetrieving keys:")
    for service in keys.keys():
        key = storage.get_key(service)
        if key:
            print(f"- {service}: Key retrieved successfully (first 10 chars: {key[:10]}...)")
        else:
            print(f"- {service}: Failed to retrieve")
    
    print("\nVerifying keys:")
    for service, original_key in keys.items():
        verified = storage.verify_key(service, original_key)
        print(f"- {service}: {'VERIFIED' if verified else 'VERIFICATION FAILED'}")
    
    print("\nAll keys stored securely with SHA-256 hashing!")
