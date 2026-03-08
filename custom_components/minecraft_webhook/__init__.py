"""The Minecraft Webhook integration for CC: Tweaked."""
from __future__ import annotations

import json
import logging
import traceback
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from aiohttp import web
from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_time_interval
import voluptuous as vol

from .const import (
    CONF_ERROR_REPORTING,
    CONF_GITHUB_TOKEN,
    CONF_SERVER_NAME,
    CONF_WEBHOOK_ID,
    DATA_CLEANUP_CANCEL,
    DATA_COMMANDS,
    DATA_COMPUTERS,
    DATA_SENSORS,
    DATA_SERVERS,
    DEFAULT_ICON,
    DEFAULT_ICONS,
    DEFAULT_UNITS,
    DOMAIN,
    ENERGY_SENSOR_KEYWORD,
    FE_ENERGY_UNIT,
    FE_POWER_UNIT,
    POWER_SENSOR_KEYWORDS,
    PROTECTED_LABEL,
    READY_DELAY_SECONDS,
    SENSOR_TYPE_BOOLEAN,
    SENSOR_TYPE_LIST,
    SENSOR_TYPE_NUMBER,
    SENSOR_TYPE_STRING,
    STALE_SENSOR_HOURS,
)
from .issue_reporter import GitHubIssueReporter

DATA_ISSUE_REPORTER = "issue_reporter"

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

# Signal for sensor updates
SIGNAL_SENSOR_UPDATE = f"{DOMAIN}_sensor_update_{{server_id}}"
SIGNAL_NEW_SENSOR = f"{DOMAIN}_new_sensor_{{server_id}}"

# Service constants
SERVICE_SEND_COMMAND = "send_command"
SERVICE_SET_OUTPUT = "set_output"
SERVICE_CLEAR_COMMANDS = "clear_commands"

ATTR_SERVER = "server"
ATTR_COMPUTER_ID = "computer_id"
ATTR_COMMAND = "command"
ATTR_DATA = "data"
ATTR_OUTPUT_NAME = "output_name"
ATTR_VALUE = "value"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Minecraft Webhook from a config entry."""
    hass.data.setdefault(DOMAIN, {
        DATA_SERVERS: {},
        DATA_SENSORS: {},
        DATA_COMMANDS: defaultdict(lambda: defaultdict(list)),
        DATA_COMPUTERS: defaultdict(dict),
    })

    # Initialise the auto error reporter (opt-in via options)
    if entry.options.get(CONF_ERROR_REPORTING) and entry.options.get(CONF_GITHUB_TOKEN):
        hass.data[DOMAIN][DATA_ISSUE_REPORTER] = GitHubIssueReporter(
            entry.options[CONF_GITHUB_TOKEN]
        )
        _LOGGER.info("Auto error reporting enabled for Minecraft Webhook")
    else:
        hass.data[DOMAIN].setdefault(DATA_ISSUE_REPORTER, None)

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

    # Register webhook with custom handler that returns responses
    webhook.async_register(
        hass,
        DOMAIN,
        f"Minecraft - {server_name}",
        webhook_id,
        _async_handle_webhook,
        allowed_methods=["GET", "POST"],
        local_only=True,
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
        manufacturer="CC: Tweaked",
        model="ComputerCraft Computer",
    )

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services (only once)
    if not hass.services.has_service(DOMAIN, SERVICE_SEND_COMMAND):
        await _async_register_services(hass)

    # Register stale sensor cleanup task (only once across all entries)
    if DATA_CLEANUP_CANCEL not in hass.data[DOMAIN]:
        hass.data[DOMAIN][DATA_CLEANUP_CANCEL] = async_track_time_interval(
            hass,
            lambda now: hass.async_create_task(_async_cleanup_stale_sensors(hass)),
            timedelta(hours=1),
        )
        _LOGGER.debug("Registered stale sensor cleanup task (runs every hour)")

    # After 30 seconds tell all known computers the integration is ready
    @callback
    def _send_ready(_now=None) -> None:
        _queue_command_for_all(hass, entry.entry_id, "ready")
        _LOGGER.info(
            "Sent 'ready' signal to computers for server '%s'", server_name
        )

    async_call_later(hass, READY_DELAY_SECONDS, _send_ready)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    webhook_id = entry.data[CONF_WEBHOOK_ID]
    server_name = entry.data[CONF_SERVER_NAME]

    # Tell all computers to pause before the webhook disappears
    _queue_command_for_all(hass, entry.entry_id, "pause")
    _LOGGER.info(
        "Sent 'pause' signal to computers for server '%s'", server_name
    )

    # Unregister webhook
    webhook.async_unregister(hass, webhook_id)

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN][DATA_SERVERS].pop(entry.entry_id, None)
        hass.data[DOMAIN][DATA_SENSORS].pop(entry.entry_id, None)

        # Close the issue reporter HTTP session
        reporter = hass.data[DOMAIN].get(DATA_ISSUE_REPORTER)
        if reporter:
            await reporter.close()
            hass.data[DOMAIN][DATA_ISSUE_REPORTER] = None

        # Cancel cleanup task when no servers remain
        if not hass.data[DOMAIN][DATA_SERVERS]:
            cancel = hass.data[DOMAIN].pop(DATA_CLEANUP_CANCEL, None)
            if cancel:
                cancel()
                _LOGGER.debug("Cancelled stale sensor cleanup task")

    return unload_ok


def _queue_command_for_all(
    hass: HomeAssistant,
    entry_id: str,
    command: str,
    data: dict | None = None,
) -> None:
    """Queue a command for every known computer on a server entry.

    Falls back to 'default' if no computers have checked in yet.
    """
    computers = hass.data[DOMAIN][DATA_COMPUTERS].get(entry_id, {})
    targets = list(computers.keys()) if computers else ["default"]

    for computer_id in targets:
        hass.data[DOMAIN][DATA_COMMANDS][entry_id][computer_id].append({
            "type": "command",
            "command": command,
            "data": data or {},
            "timestamp": datetime.now().isoformat(),
        })

    _LOGGER.debug(
        "Queued '%s' for %d computer(s) on entry %s",
        command,
        len(targets),
        entry_id,
    )


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register integration services."""

    async def async_send_command(call: ServiceCall) -> None:
        """Send a command to a CC: Tweaked computer."""
        server = call.data[ATTR_SERVER]
        computer_id = call.data[ATTR_COMPUTER_ID]
        command = call.data[ATTR_COMMAND]
        data = call.data.get(ATTR_DATA, {})

        # Find the server entry
        entry_id = _find_server_entry(hass, server)
        if entry_id is None:
            _LOGGER.error("Server '%s' not found", server)
            return

        # Queue the command
        cmd = {
            "type": "command",
            "command": command,
            "data": data,
            "timestamp": datetime.now().isoformat(),
        }
        hass.data[DOMAIN][DATA_COMMANDS][entry_id][computer_id].append(cmd)
        _LOGGER.debug("Queued command for computer %s: %s", computer_id, command)

    async def async_set_output(call: ServiceCall) -> None:
        """Set an output value for a CC: Tweaked computer to read."""
        server = call.data[ATTR_SERVER]
        computer_id = call.data[ATTR_COMPUTER_ID]
        output_name = call.data[ATTR_OUTPUT_NAME]
        value = call.data[ATTR_VALUE]

        # Find the server entry
        entry_id = _find_server_entry(hass, server)
        if entry_id is None:
            _LOGGER.error("Server '%s' not found", server)
            return

        # Store the output value
        if entry_id not in hass.data[DOMAIN][DATA_COMPUTERS]:
            hass.data[DOMAIN][DATA_COMPUTERS][entry_id] = {}
        if computer_id not in hass.data[DOMAIN][DATA_COMPUTERS][entry_id]:
            hass.data[DOMAIN][DATA_COMPUTERS][entry_id][computer_id] = {"outputs": {}}

        hass.data[DOMAIN][DATA_COMPUTERS][entry_id][computer_id]["outputs"][output_name] = value
        _LOGGER.debug("Set output %s=%s for computer %s", output_name, value, computer_id)

    async def async_clear_commands(call: ServiceCall) -> None:
        """Clear pending commands for a computer."""
        server = call.data[ATTR_SERVER]
        computer_id = call.data.get(ATTR_COMPUTER_ID)

        entry_id = _find_server_entry(hass, server)
        if entry_id is None:
            _LOGGER.error("Server '%s' not found", server)
            return

        if computer_id:
            hass.data[DOMAIN][DATA_COMMANDS][entry_id][computer_id] = []
            _LOGGER.debug("Cleared commands for computer %s", computer_id)
        else:
            hass.data[DOMAIN][DATA_COMMANDS][entry_id] = defaultdict(list)
            _LOGGER.debug("Cleared all commands for server %s", server)

    # Register services with schemas
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_COMMAND,
        async_send_command,
        schema=vol.Schema({
            vol.Required(ATTR_SERVER): cv.string,
            vol.Required(ATTR_COMPUTER_ID): cv.string,
            vol.Required(ATTR_COMMAND): cv.string,
            vol.Optional(ATTR_DATA, default={}): dict,
        }),
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_OUTPUT,
        async_set_output,
        schema=vol.Schema({
            vol.Required(ATTR_SERVER): cv.string,
            vol.Required(ATTR_COMPUTER_ID): cv.string,
            vol.Required(ATTR_OUTPUT_NAME): cv.string,
            vol.Required(ATTR_VALUE): vol.Any(str, int, float, bool, list, dict),
        }),
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_COMMANDS,
        async_clear_commands,
        schema=vol.Schema({
            vol.Required(ATTR_SERVER): cv.string,
            vol.Optional(ATTR_COMPUTER_ID): cv.string,
        }),
    )


def _find_server_entry(hass: HomeAssistant, server_name: str) -> str | None:
    """Find entry ID by server name."""
    for entry_id, server_data in hass.data[DOMAIN][DATA_SERVERS].items():
        if server_data["name"].lower() == server_name.lower():
            return entry_id
    return None


async def _async_handle_webhook(
    hass: HomeAssistant,
    webhook_id: str,
    request: web.Request,
) -> web.Response:
    """Handle incoming webhook requests from CC: Tweaked."""
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
        return web.Response(status=404, text="Server not found")

    # Handle GET request - return pending commands
    if request.method == "GET":
        return await _handle_get_commands(hass, entry_id, request)

    # Handle POST request - receive data
    if request.method == "POST":
        return await _handle_post_data(hass, entry_id, server_name, request)

    return web.Response(status=405, text="Method not allowed")


async def _handle_get_commands(
    hass: HomeAssistant,
    entry_id: str,
    request: web.Request,
) -> web.Response:
    """Handle GET request - return pending commands for a computer."""
    computer_id = request.query.get("computer_id", request.query.get("id", "default"))

    # Get pending commands
    commands = hass.data[DOMAIN][DATA_COMMANDS][entry_id].get(computer_id, [])

    # Get stored outputs
    outputs = {}
    if entry_id in hass.data[DOMAIN][DATA_COMPUTERS]:
        if computer_id in hass.data[DOMAIN][DATA_COMPUTERS][entry_id]:
            outputs = hass.data[DOMAIN][DATA_COMPUTERS][entry_id][computer_id].get("outputs", {})

    # Build response
    response_data = {
        "commands": commands,
        "outputs": outputs,
        "timestamp": datetime.now().isoformat(),
    }

    # Clear commands after sending (they've been retrieved)
    hass.data[DOMAIN][DATA_COMMANDS][entry_id][computer_id] = []

    _LOGGER.debug(
        "Returning %d commands and %d outputs for computer %s",
        len(commands),
        len(outputs),
        computer_id,
    )

    return web.json_response(response_data)


async def _handle_post_data(
    hass: HomeAssistant,
    entry_id: str,
    server_name: str,
    request: web.Request,
) -> web.Response:
    """Handle POST request - receive data from CC: Tweaked."""
    try:
        data = await request.json()
    except (ValueError, json.JSONDecodeError) as exc:
        _LOGGER.error("Received invalid JSON from Minecraft webhook")
        await _report_error(
            hass, "InvalidJSON", str(exc), traceback.format_exc(),
            {"server": server_name},
        )
        return web.Response(status=400, text="Invalid JSON")

    # Extract computer_id if provided
    computer_id = data.pop("_computer_id", data.pop("computer_id", "default"))

    _LOGGER.debug(
        "Received data from computer '%s' on server '%s': %s",
        computer_id,
        server_name,
        data,
    )

    # Update last update time
    hass.data[DOMAIN][DATA_SERVERS][entry_id]["last_update"] = datetime.now()
    hass.data[DOMAIN][DATA_SERVERS][entry_id]["data"] = data

    # Track computer
    if entry_id not in hass.data[DOMAIN][DATA_COMPUTERS]:
        hass.data[DOMAIN][DATA_COMPUTERS][entry_id] = {}
    if computer_id not in hass.data[DOMAIN][DATA_COMPUTERS][entry_id]:
        hass.data[DOMAIN][DATA_COMPUTERS][entry_id][computer_id] = {"outputs": {}}
    hass.data[DOMAIN][DATA_COMPUTERS][entry_id][computer_id]["last_seen"] = datetime.now()

    # Process the data and create/update sensors
    try:
        await _process_webhook_data(hass, entry_id, computer_id, data)
    except Exception as exc:
        _LOGGER.error("Error processing webhook data from %s: %s", computer_id, exc)
        await _report_error(
            hass, "WebhookProcessingError", str(exc), traceback.format_exc(),
            {"computer_id": computer_id, "server": server_name},
        )

    # Return any pending commands immediately
    commands = hass.data[DOMAIN][DATA_COMMANDS][entry_id].get(computer_id, [])
    outputs = hass.data[DOMAIN][DATA_COMPUTERS][entry_id][computer_id].get("outputs", {})

    response_data = {
        "status": "ok",
        "commands": commands,
        "outputs": outputs,
    }

    # Clear commands after sending
    hass.data[DOMAIN][DATA_COMMANDS][entry_id][computer_id] = []

    return web.json_response(response_data)


async def _process_webhook_data(
    hass: HomeAssistant,
    entry_id: str,
    computer_id: str,
    data: dict[str, Any],
) -> None:
    """Process webhook data and create/update sensors."""
    sensors = hass.data[DOMAIN][DATA_SENSORS][entry_id]
    new_sensors = []

    # Add computer_id prefix if not default
    prefix = f"{computer_id}_" if computer_id != "default" else ""

    def flatten_data(d: dict[str, Any], parent_key: str = "") -> dict[str, Any]:
        """Flatten nested dictionary."""
        items = {}
        for key, value in d.items():
            # Skip internal keys
            if key.startswith("_"):
                continue

            new_key = f"{parent_key}_{key}" if parent_key else key
            new_key = new_key.lower().replace(" ", "_").replace("-", "_")
            full_key = f"{prefix}{new_key}"

            if isinstance(value, dict):
                items.update(flatten_data(value, new_key))
            elif isinstance(value, list):
                items[full_key] = {
                    "value": len(value),
                    "type": SENSOR_TYPE_LIST,
                    "raw": value,
                }
            elif isinstance(value, bool):
                items[full_key] = {
                    "value": value,
                    "type": SENSOR_TYPE_BOOLEAN,
                }
            elif isinstance(value, (int, float)):
                items[full_key] = {
                    "value": value,
                    "type": SENSOR_TYPE_NUMBER,
                }
            else:
                items[full_key] = {
                    "value": str(value) if value is not None else None,
                    "type": SENSOR_TYPE_STRING,
                }
        return items

    flat_data = flatten_data(data)

    for sensor_key, sensor_data in flat_data.items():
        if sensor_key not in sensors:
            sensors[sensor_key] = {
                "key": sensor_key,
                "type": sensor_data["type"],
                "value": sensor_data["value"],
                "icon": _get_icon_for_key(sensor_key),
                "unit": _get_unit_for_key(sensor_key),
                "device_class": _get_device_class_for_key(sensor_key),
                "attributes": sensor_data.get("raw"),
                "computer_id": computer_id,
                "last_seen": datetime.now(),
            }
            new_sensors.append(sensor_key)
            _LOGGER.info("Discovered new sensor: %s", sensor_key)
        else:
            sensors[sensor_key]["value"] = sensor_data["value"]
            sensors[sensor_key]["attributes"] = sensor_data.get("raw")
            sensors[sensor_key]["last_seen"] = datetime.now()

    if new_sensors:
        async_dispatcher_send(
            hass,
            SIGNAL_NEW_SENSOR.format(server_id=entry_id),
            new_sensors,
        )

    async_dispatcher_send(
        hass,
        SIGNAL_SENSOR_UPDATE.format(server_id=entry_id),
    )


async def _async_cleanup_stale_sensors(hass: HomeAssistant) -> None:
    """Delete sensors that haven't received data in 24+ hours.

    Sensors with the HA label 'never' are permanently protected from deletion.
    """
    entity_reg = er.async_get(hass)
    cutoff = datetime.now() - timedelta(hours=STALE_SENSOR_HOURS)

    for entry_id, sensors in hass.data[DOMAIN][DATA_SENSORS].items():
        keys_to_remove = []

        for sensor_key, sensor_data in sensors.items():
            last_seen = sensor_data.get("last_seen")

            # Skip sensors that have never been updated (just created)
            if last_seen is None:
                continue

            # Skip sensors that are still fresh
            if last_seen >= cutoff:
                continue

            # Determine which platform this sensor lives on
            platform = (
                Platform.BINARY_SENSOR
                if sensor_data.get("type") == SENSOR_TYPE_BOOLEAN
                else Platform.SENSOR
            )

            unique_id = f"{DOMAIN}_{entry_id}_{sensor_key}"
            entity_id = entity_reg.async_get_entity_id(platform, DOMAIN, unique_id)

            if entity_id:
                entity_entry = entity_reg.async_get(entity_id)
                # Respect the 'never' label — skip protected sensors
                if entity_entry and PROTECTED_LABEL in (entity_entry.labels or set()):
                    _LOGGER.debug(
                        "Skipping stale sensor %s (protected by '%s' label)",
                        entity_id,
                        PROTECTED_LABEL,
                    )
                    continue

                entity_reg.async_remove(entity_id)
                _LOGGER.info(
                    "Removed stale sensor %s (no data for %d+ hours)",
                    entity_id,
                    STALE_SENSOR_HOURS,
                )

            keys_to_remove.append(sensor_key)

        for key in keys_to_remove:
            sensors.pop(key, None)


async def _report_error(
    hass: HomeAssistant,
    error_type: str,
    error_message: str,
    error_traceback: str | None = None,
    extra: dict | None = None,
) -> None:
    """Forward an error to GitHub if the reporter is configured."""
    try:
        reporter: GitHubIssueReporter | None = hass.data.get(DOMAIN, {}).get(DATA_ISSUE_REPORTER)
        if reporter:
            info = extra or {}
            info["ha_version"] = hass.config.version
            await reporter.report_error(
                error_type=error_type,
                error_message=error_message,
                tb=error_traceback,
                extra=info,
            )
    except Exception as exc:
        _LOGGER.debug("Failed to forward error to GitHub reporter: %s", exc)


def _get_icon_for_key(key: str) -> str:
    """Get an appropriate icon for a sensor key."""
    if key in DEFAULT_ICONS:
        return DEFAULT_ICONS[key]
    for keyword, icon in DEFAULT_ICONS.items():
        if keyword in key:
            return icon
    return DEFAULT_ICON


def _get_device_class_for_key(key: str) -> str | None:
    """Return HA device class string for a sensor key, or None.

    Power keywords are checked first because 'energy_rate' also contains 'energy'.
    Returns 'power' or 'energy' as strings; sensor.py converts to SensorDeviceClass.
    """
    if any(kw in key for kw in POWER_SENSOR_KEYWORDS):
        return "power"
    if ENERGY_SENSOR_KEYWORD in key and "percent" not in key:
        return "energy"
    return None


def _get_unit_for_key(key: str) -> str | None:
    """Get an appropriate unit for a sensor key."""
    # Energy/power fields override DEFAULT_UNITS
    device_class = _get_device_class_for_key(key)
    if device_class == "energy":
        return FE_ENERGY_UNIT
    if device_class == "power":
        return FE_POWER_UNIT

    if key in DEFAULT_UNITS:
        return DEFAULT_UNITS[key]
    for keyword, unit in DEFAULT_UNITS.items():
        if keyword in key:
            return unit
    return None


def get_webhook_url(hass: HomeAssistant, webhook_id: str) -> str:
    """Get the full webhook URL."""
    return webhook.async_generate_url(hass, webhook_id)
