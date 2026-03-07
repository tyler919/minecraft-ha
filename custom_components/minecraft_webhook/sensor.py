"""Sensor platform for Minecraft Webhook integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
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
    SENSOR_TYPE_LIST,
    SENSOR_TYPE_NUMBER,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Minecraft sensors based on a config entry."""
    server_name = entry.data[CONF_SERVER_NAME]

    # Track which sensors we've created
    created_sensors: set[str] = set()

    @callback
    def async_add_new_sensors(sensor_keys: list[str]) -> None:
        """Add new sensors when discovered."""
        sensors_data = hass.data[DOMAIN][DATA_SENSORS].get(entry.entry_id, {})
        new_entities = []

        for key in sensor_keys:
            if key in created_sensors:
                continue

            sensor_info = sensors_data.get(key)
            if sensor_info is None:
                continue

            # Skip boolean types - they go to binary_sensor
            if sensor_info["type"] == SENSOR_TYPE_BOOLEAN:
                continue

            new_entities.append(
                MinecraftSensor(
                    hass=hass,
                    entry=entry,
                    server_name=server_name,
                    sensor_key=key,
                    sensor_info=sensor_info,
                )
            )
            created_sensors.add(key)
            _LOGGER.debug("Creating sensor: minecraft_%s_%s", server_name, key)

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


class MinecraftSensor(SensorEntity):
    """Representation of a Minecraft sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        server_name: str,
        sensor_key: str,
        sensor_info: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        self.hass = hass
        self._entry = entry
        self._server_name = server_name
        self._sensor_key = sensor_key
        self._sensor_info = sensor_info

        # Slugify server name for entity ID
        slug_server = server_name.lower().replace(" ", "_").replace("-", "_")

        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{sensor_key}"
        self._attr_name = sensor_key.replace("_", " ").title()
        self._attr_icon = sensor_info.get("icon", "mdi:minecraft")
        self._attr_native_unit_of_measurement = sensor_info.get("unit")

        # Apply device class for energy / power sensors
        device_class_str = sensor_info.get("device_class")
        if device_class_str:
            try:
                self._attr_device_class = SensorDeviceClass(device_class_str)
            except ValueError:
                pass  # unknown class string — leave unset

        # Set state class for numeric sensors
        if sensor_info["type"] == SENSOR_TYPE_NUMBER:
            self._attr_state_class = SensorStateClass.MEASUREMENT

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
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        sensors = self.hass.data[DOMAIN][DATA_SENSORS].get(self._entry.entry_id, {})
        sensor_data = sensors.get(self._sensor_key, {})
        return sensor_data.get("value")

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional state attributes."""
        sensors = self.hass.data[DOMAIN][DATA_SENSORS].get(self._entry.entry_id, {})
        sensor_data = sensors.get(self._sensor_key, {})

        attrs = {}

        # Add raw list data as attribute
        raw_data = sensor_data.get("attributes")
        if raw_data is not None:
            if isinstance(raw_data, list):
                attrs["items"] = raw_data
                attrs["count"] = len(raw_data)
            else:
                attrs["raw_data"] = raw_data

        # Add last update time
        server_data = self.hass.data[DOMAIN][DATA_SERVERS].get(self._entry.entry_id, {})
        last_update = server_data.get("last_update")
        if last_update:
            attrs["last_update"] = last_update.isoformat()

        return attrs if attrs else None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        sensors = self.hass.data[DOMAIN][DATA_SENSORS].get(self._entry.entry_id, {})
        return self._sensor_key in sensors
