"""Binary sensor platform for Minecraft Webhook integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SIGNAL_NEW_SENSOR, SIGNAL_SENSOR_UPDATE
from .const import (
    CONF_SERVER_NAME,
    DATA_SENSORS,
    DATA_SERVERS,
    DOMAIN,
    SENSOR_TYPE_BOOLEAN,
)

_LOGGER = logging.getLogger(__name__)

# Map sensor keys to device classes
DEVICE_CLASS_MAP = {
    "online": BinarySensorDeviceClass.CONNECTIVITY,
    "server_online": BinarySensorDeviceClass.CONNECTIVITY,
    "is_online": BinarySensorDeviceClass.CONNECTIVITY,
    "running": BinarySensorDeviceClass.RUNNING,
    "is_running": BinarySensorDeviceClass.RUNNING,
    "raining": BinarySensorDeviceClass.MOISTURE,
    "is_raining": BinarySensorDeviceClass.MOISTURE,
    "thundering": BinarySensorDeviceClass.MOISTURE,
    "is_thundering": BinarySensorDeviceClass.MOISTURE,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Minecraft binary sensors based on a config entry."""
    server_name = entry.data[CONF_SERVER_NAME]

    # Track which sensors we've created
    created_sensors: set[str] = set()

    @callback
    def async_add_new_sensors(sensor_keys: list[str]) -> None:
        """Add new binary sensors when discovered."""
        sensors_data = hass.data[DOMAIN][DATA_SENSORS].get(entry.entry_id, {})
        new_entities = []

        for key in sensor_keys:
            if key in created_sensors:
                continue

            sensor_info = sensors_data.get(key)
            if sensor_info is None:
                continue

            # Only handle boolean types
            if sensor_info["type"] != SENSOR_TYPE_BOOLEAN:
                continue

            new_entities.append(
                MinecraftBinarySensor(
                    hass=hass,
                    entry=entry,
                    server_name=server_name,
                    sensor_key=key,
                    sensor_info=sensor_info,
                )
            )
            created_sensors.add(key)
            _LOGGER.debug("Creating binary sensor: minecraft_%s_%s", server_name, key)

        if new_entities:
            async_add_entities(new_entities)

    # Listen for new sensor discoveries
    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            SIGNAL_NEW_SENSOR.format(server_id=entry.entry_id),
            async_add_new_sensors,
        )
    )

    # Add any existing sensors (in case of restart)
    existing_sensors = list(hass.data[DOMAIN][DATA_SENSORS].get(entry.entry_id, {}).keys())
    if existing_sensors:
        async_add_new_sensors(existing_sensors)


class MinecraftBinarySensor(BinarySensorEntity):
    """Representation of a Minecraft binary sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        server_name: str,
        sensor_key: str,
        sensor_info: dict[str, Any],
    ) -> None:
        """Initialize the binary sensor."""
        self.hass = hass
        self._entry = entry
        self._server_name = server_name
        self._sensor_key = sensor_key
        self._sensor_info = sensor_info

        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{sensor_key}"
        self._attr_name = sensor_key.replace("_", " ").title()

        # Set device class based on key
        for keyword, device_class in DEVICE_CLASS_MAP.items():
            if keyword in sensor_key.lower():
                self._attr_device_class = device_class
                break

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Minecraft - {server_name}",
            manufacturer="Minecraft",
            model="Java Edition Server",
        )

    async def async_added_to_hass(self) -> None:
        """Register callbacks when entity is added."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_SENSOR_UPDATE.format(server_id=self._entry.entry_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        """Handle updated data."""
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        sensors = self.hass.data[DOMAIN][DATA_SENSORS].get(self._entry.entry_id, {})
        sensor_data = sensors.get(self._sensor_key, {})
        value = sensor_data.get("value")

        if value is None:
            return None

        # Handle various truthy values
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "yes", "on", "1")
        if isinstance(value, (int, float)):
            return value > 0

        return bool(value)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional state attributes."""
        server_data = self.hass.data[DOMAIN][DATA_SERVERS].get(self._entry.entry_id, {})
        last_update = server_data.get("last_update")

        if last_update:
            return {"last_update": last_update.isoformat()}
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        sensors = self.hass.data[DOMAIN][DATA_SENSORS].get(self._entry.entry_id, {})
        return self._sensor_key in sensors
