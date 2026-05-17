"""DCC Manager - Factory for creating and managing DCC instances."""

from typing import Optional

from launcher.core.config_manager import config_manager
from launcher.dcc.base_dcc import BaseDCC
from launcher.dcc.dcc_maya import MayaDCC
from launcher.dcc.dcc_houdini import HoudiniDCC
from launcher.dcc.dcc_nuke import NukeDCC


class DCCManager:
    """Manages DCC instances and provides factory access."""

    _instance = None
    _dcc_cache: dict[str, BaseDCC] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self._dcc_classes = {
            "maya": MayaDCC,
            "houdini": HoudiniDCC,
            "nuke": NukeDCC,
        }

    def get_dcc(self, role: str) -> Optional[BaseDCC]:
        """Get or create DCC instance by role.

        Args:
            role: DCC role name (maya, houdini, nuke).

        Returns:
            DCC instance or None if not found.
        """
        role = role.lower()

        if role in self._dcc_cache:
            return self._dcc_cache[role]

        # Get config from config_manager
        dcc_config = config_manager.get_dcc_by_role(role)
        if not dcc_config:
            return None

        dcc_class = self._dcc_classes.get(role)
        if not dcc_class:
            return None

        dcc_instance = dcc_class(dcc_config)
        self._dcc_cache[role] = dcc_instance
        return dcc_instance

    def get_available_dccs(self) -> list[str]:
        """Get list of available DCC role names.

        Returns:
            List of DCC role identifiers.
        """
        return list(self._dcc_classes.keys())

    def list_all_configured_dccs(self) -> dict[str, dict]:
        """Get all DCC configurations.

        Returns:
            Dictionary of DCC configs by role.
        """
        dcc_config = config_manager.get_dcc_config()
        return dcc_config.get("dcc", {})

    def reload(self):
        """Clear cache and reload DCC instances."""
        self._dcc_cache.clear()


# Singleton instance
dcc_manager = DCCManager()