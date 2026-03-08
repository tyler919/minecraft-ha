"""Diagnostics support for Minecraft Webhook integration."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    DATA_COMMANDS,
    DATA_COMPUTERS,
    DATA_SENSORS,
    DATA_SERVERS,
    DOMAIN,
)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    entry_id = entry.entry_id

    server_data = hass.data[DOMAIN][DATA_SERVERS].get(entry_id, {})
    sensors = hass.data[DOMAIN][DATA_SENSORS].get(entry_id, {})
    computers = hass.data[DOMAIN][DATA_COMPUTERS].get(entry_id, {})
    commands = hass.data[DOMAIN][DATA_COMMANDS].get(entry_id, {})

    # Build per-computer summary
    computer_info: dict[str, Any] = {}
    for cid, cdata in computers.items():
        last_seen = cdata.get("last_seen")
        computer_info[cid] = {
            "last_seen": last_seen.isoformat() if last_seen else None,
            "pending_commands": len(commands.get(cid, [])),
            "outputs": list(cdata.get("outputs", {}).keys()),
        }

    # Count sensors grouped by computer → peripheral device
    sensor_summary: dict[str, Any] = {}
    for key, sdata in sensors.items():
        cid = sdata.get("computer_id", "unknown")
        did = sdata.get("device_id", cid)
        if cid not in sensor_summary:
            sensor_summary[cid] = {"total": 0, "peripherals": {}}
        sensor_summary[cid]["total"] += 1
        if did not in sensor_summary[cid]["peripherals"]:
            sensor_summary[cid]["peripherals"][did] = 0
        sensor_summary[cid]["peripherals"][did] += 1

    last_update = server_data.get("last_update")

    return {
        "server": {
            "name": server_data.get("name"),
            "last_update": last_update.isoformat() if last_update else None,
            "total_sensors": len(sensors),
            "total_computers": len(computers),
        },
        "computers": computer_info,
        "sensors_by_computer_and_peripheral": sensor_summary,
    }
