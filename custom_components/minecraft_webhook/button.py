"""Button platform for Minecraft Webhook integration."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SIGNAL_NEW_COMPUTER
from .const import (
    CONF_SERVER_NAME,
    DATA_COMMANDS,
    DATA_COMPUTERS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# Buttons to create per computer
_COMPUTER_BUTTONS = [
    {
        "id": "scan_now",
        "label": "Scan Now",
        "icon": "mdi:radar",
    },
    {
        "id": "setup",
        "label": "Run Setup",
        "icon": "mdi:cog",
    },
    {
        "id": "reboot",
        "label": "Reboot",
        "icon": "mdi:restart",
    },
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Minecraft buttons based on a config entry."""
    created_computers: set[str] = set()

    @callback
    def async_add_computer_buttons(computer_id: str) -> None:
        """Add buttons when a new computer is discovered."""
        if computer_id in created_computers:
            return

        created_computers.add(computer_id)
        new_entities = [
            MinecraftComputerButton(
                hass=hass,
                entry=entry,
                computer_id=computer_id,
                button_def=btn,
            )
            for btn in _COMPUTER_BUTTONS
        ]
        async_add_entities(new_entities)
        _LOGGER.debug("Created %d buttons for computer '%s'", len(new_entities), computer_id)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            SIGNAL_NEW_COMPUTER.format(server_id=entry.entry_id),
            async_add_computer_buttons,
        )
    )

    # Add buttons for computers already known (in case of HA restart)
    for computer_id in hass.data[DOMAIN][DATA_COMPUTERS].get(entry.entry_id, {}):
        async_add_computer_buttons(computer_id)


class MinecraftComputerButton(ButtonEntity):
    """A button that queues a command to a specific CC: Tweaked computer."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        computer_id: str,
        button_def: dict[str, Any],
    ) -> None:
        """Initialize the button."""
        self.hass = hass
        self._entry = entry
        self._computer_id = computer_id
        self._command = button_def["id"]

        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{computer_id}_{self._command}"
        self._attr_name = button_def["label"]
        self._attr_icon = button_def["icon"]

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{computer_id}")},
        )

    async def async_press(self) -> None:
        """Handle the button press — queue a command for the computer."""
        cmd = {
            "type": "command",
            "command": self._command,
            "data": {},
            "timestamp": datetime.now().isoformat(),
        }
        self.hass.data[DOMAIN][DATA_COMMANDS][self._entry.entry_id][self._computer_id].append(cmd)
        _LOGGER.debug(
            "Queued '%s' command for computer '%s'",
            self._command,
            self._computer_id,
        )
