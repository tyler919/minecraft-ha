"""The Minecraft Webhook integration."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_SERVER_NAME,
    CONF_WEBHOOK_ID,
    DATA_SENSORS,
    DATA_SERVERS,
    DEFAULT_ICON,
    DEFAULT_ICONS,
    DEFAULT_UNITS,
    DOMAIN,
    SENSOR_TYPE_BOOLEAN,
    SENSOR_TYPE_DICT,
    SENSOR_TYPE_LIST,
    SENSOR_TYPE_NUMBER,
    SENSOR_TYPE_STRING,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

# Signal for sensor updates
SIGNAL_SENSOR_UPDATE = f"{DOMAIN}_sensor_update_{{server_id}}"
SIGNAL_NEW_SENSOR = f"{DOMAIN}_new_sensor_{{server_id}}"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Minecraft Webhook from a config entry."""
    hass.data.setdefault(DOMAIN, {DATA_SERVERS: {}, DATA_SENSORS: {}})

    server_name = entry.data[CONF_SERVER_NAME]
    webhook_id = entry.data[CONF_WEBHOOK_ID]

    # Store server data
    hass.data[DOMAIN][DATA_SERVERS][entry.entry_id] = {
        "name": server_name,
        "webhook_id": webhook_id,
        "last_update": None,
        "data": {},
    }

    # Initialize sensors storage for this server
    hass.data[DOMAIN][DATA_SENSORS][entry.entry_id] = {}

    # Register webhook
    webhook.async_register(
        hass,
        DOMAIN,
        f"Minecraft - {server_name}",
        webhook_id,
        _async_handle_webhook,
    )

    _LOGGER.info(
        "Registered webhook for Minecraft server '%s' at /api/webhook/%s",
        server_name,
        webhook_id,
    )

    # Register device
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"Minecraft - {server_name}",
        manufacturer="Minecraft",
        model="Java Edition Server",
    )

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    webhook_id = entry.data[CONF_WEBHOOK_ID]

    # Unregister webhook
    webhook.async_unregister(hass, webhook_id)

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Clean up data
        hass.data[DOMAIN][DATA_SERVERS].pop(entry.entry_id, None)
        hass.data[DOMAIN][DATA_SENSORS].pop(entry.entry_id, None)

    return unload_ok


async def _async_handle_webhook(
    hass: HomeAssistant,
    webhook_id: str,
    request,
) -> None:
    """Handle incoming webhook data from Minecraft."""
    try:
        data = await request.json()
    except ValueError:
        _LOGGER.error("Received invalid JSON from Minecraft webhook")
        return

    # Find the entry for this webhook
    entry_id = None
    server_name = None
    for eid, server_data in hass.data[DOMAIN][DATA_SERVERS].items():
        if server_data["webhook_id"] == webhook_id:
            entry_id = eid
            server_name = server_data["name"]
            break

    if entry_id is None:
        _LOGGER.error("Received webhook for unknown server: %s", webhook_id)
        return

    _LOGGER.debug(
        "Received webhook data for server '%s': %s",
        server_name,
        data,
    )

    # Update last update time
    hass.data[DOMAIN][DATA_SERVERS][entry_id]["last_update"] = datetime.now()
    hass.data[DOMAIN][DATA_SERVERS][entry_id]["data"] = data

    # Process the data and create/update sensors
    await _process_webhook_data(hass, entry_id, data)


async def _process_webhook_data(
    hass: HomeAssistant,
    entry_id: str,
    data: dict[str, Any],
    prefix: str = "",
) -> None:
    """Process webhook data and create/update sensors."""
    sensors = hass.data[DOMAIN][DATA_SENSORS][entry_id]
    new_sensors = []

    def flatten_data(d: dict[str, Any], parent_key: str = "") -> dict[str, Any]:
        """Flatten nested dictionary."""
        items = {}
        for key, value in d.items():
            new_key = f"{parent_key}_{key}" if parent_key else key
            new_key = new_key.lower().replace(" ", "_").replace("-", "_")

            if isinstance(value, dict):
                # For nested dicts, flatten them
                items.update(flatten_data(value, new_key))
            elif isinstance(value, list):
                # Store lists as the count with full list in attributes
                items[new_key] = {
                    "value": len(value),
                    "type": SENSOR_TYPE_LIST,
                    "raw": value,
                }
            elif isinstance(value, bool):
                items[new_key] = {
                    "value": value,
                    "type": SENSOR_TYPE_BOOLEAN,
                }
            elif isinstance(value, (int, float)):
                items[new_key] = {
                    "value": value,
                    "type": SENSOR_TYPE_NUMBER,
                }
            else:
                items[new_key] = {
                    "value": str(value) if value is not None else None,
                    "type": SENSOR_TYPE_STRING,
                }
        return items

    # Flatten the incoming data
    flat_data = flatten_data(data)

    # Update or create sensors
    for sensor_key, sensor_data in flat_data.items():
        if sensor_key not in sensors:
            # New sensor discovered
            sensors[sensor_key] = {
                "key": sensor_key,
                "type": sensor_data["type"],
                "value": sensor_data["value"],
                "icon": _get_icon_for_key(sensor_key),
                "unit": _get_unit_for_key(sensor_key),
                "attributes": sensor_data.get("raw"),
            }
            new_sensors.append(sensor_key)
            _LOGGER.info("Discovered new sensor: %s", sensor_key)
        else:
            # Update existing sensor
            sensors[sensor_key]["value"] = sensor_data["value"]
            sensors[sensor_key]["attributes"] = sensor_data.get("raw")

    # Signal new sensors to be created
    if new_sensors:
        async_dispatcher_send(
            hass,
            SIGNAL_NEW_SENSOR.format(server_id=entry_id),
            new_sensors,
        )

    # Signal all sensors to update
    async_dispatcher_send(
        hass,
        SIGNAL_SENSOR_UPDATE.format(server_id=entry_id),
    )


def _get_icon_for_key(key: str) -> str:
    """Get an appropriate icon for a sensor key."""
    # Check for exact match first
    if key in DEFAULT_ICONS:
        return DEFAULT_ICONS[key]

    # Check if key contains any known keywords
    for keyword, icon in DEFAULT_ICONS.items():
        if keyword in key:
            return icon

    return DEFAULT_ICON


def _get_unit_for_key(key: str) -> str | None:
    """Get an appropriate unit for a sensor key."""
    # Check for exact match first
    if key in DEFAULT_UNITS:
        return DEFAULT_UNITS[key]

    # Check if key contains any known keywords
    for keyword, unit in DEFAULT_UNITS.items():
        if keyword in key:
            return unit

    return None


def get_webhook_url(hass: HomeAssistant, webhook_id: str) -> str:
    """Get the full webhook URL."""
    return webhook.async_generate_url(hass, webhook_id)
