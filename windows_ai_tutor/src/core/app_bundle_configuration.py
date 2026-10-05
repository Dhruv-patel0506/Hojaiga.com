"""
App Bundle Configuration - Runtime Configuration (Clicky-style)

Helper for reading runtime configuration.
Converted from AppBundleConfiguration.swift to Windows Python.
Uses ConfigManager for Windows instead of Info.plist.
"""

from typing import Optional
from ..utils.config import ConfigManager
from ..utils.logger import setup_logger


class AppBundleConfiguration:
    """Runtime configuration reader."""

    _config_manager = None

    @classmethod
    def _get_config_manager(cls) -> ConfigManager:
        """Get the config manager instance."""
        if cls._config_manager is None:
            cls._config_manager = ConfigManager()
        return cls._config_manager

    @classmethod
    def string_value(cls, for_key: str) -> Optional[str]:
        """
        Get a string value from configuration.

        Args:
            for_key: Configuration key

        Returns:
            String value or None if not found
        """
        config = cls._get_config_manager()
        value = config.get(for_key)

        if value is None:
            return None

        trimmed_value = str(value).strip()
        return trimmed_value if trimmed_value else None

    @classmethod
    def bool_value(cls, for_key: str, default: bool = False) -> bool:
        """
        Get a boolean value from configuration.

        Args:
            for_key: Configuration key
            default: Default value if not found

        Returns:
            Boolean value
        """
        config = cls._get_config_manager()
        value = config.get(for_key)

        if value is None:
            return default

        return bool(value)

    @classmethod
    def int_value(cls, for_key: str, default: int = 0) -> int:
        """
        Get an integer value from configuration.

        Args:
            for_key: Configuration key
            default: Default value if not found

        Returns:
            Integer value
        """
        config = cls._get_config_manager()
        value = config.get(for_key)

        if value is None:
            return default

        try:
            return int(value)
        except (ValueError, TypeError):
            return default
