"""Auto-generated Lovelace dashboard for Minecraft Webhook integration.

One dashboard is created per server entry.  It is populated with the
sensors that exist at generation time, so call async_regenerate_dashboard
(or use the minecraft_webhook.regenerate_dashboard service) after your
CC: Tweaked scanner has sent its first scan and all peripherals appear.

Dashboard structure
-------------------
  View: {server_name}
    ├── Overview glance card         (online, label, uptime, periph_count)
    └── [For each computer]
          Markdown heading
          Glance  — Status           (online, label, uptime, periph_count)
          Entities — Turtle Info     (fuel %, fuel, max fuel)   if turtle
          [For each peripheral]
            Gauge    — {Periph} %    (if a *_percent field exists)
            Entities — {Periph}      (all non-type sensor fields)
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store

from .const import (
    CONF_SERVER_NAME,
    DATA_SENSORS,
    DOMAIN,
    SENSOR_TYPE_BOOLEAN,
)

_LOGGER = logging.getLogger(__name__)

_STORAGE_VERSION = 1
_STORAGE_MINOR_VERSION = 2

# How long after setup_entry to auto-regenerate (gives time for first scan)
_AUTO_REGEN_DELAY = 45

# Peripheral type → friendly label
_TYPE_LABELS: dict[str, str] = {
    "energy_storage":       "Energy Storage",
    "energystorage":        "Energy Storage",
    "energy_detector":      "Energy Detector",
    "energydetector":       "Energy Detector",
    "inventory":            "Inventory",
    "drive":                "Disk Drive",
    "me_bridge":            "ME System",
    "mebridge":             "ME System",
    "rs_bridge":            "Refined Storage",
    "rsbridge":             "Refined Storage",
    "environment_detector": "Environment",
    "environmentdetector":  "Environment",
    "player_detector":      "Player Detection",
    "playerdetector":       "Player Detection",
    "fluid_storage":        "Fluid Tank",
    "fluidstorage":         "Fluid Tank",
    "monitor":              "Monitor",
    "modem":                "Modem",
    "printer":              "Printer",
    "computer":             "Computer",
}


def _slug(text: str) -> str:
    """Convert text to a URL/storage-safe slug."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _type_label(ptype: str) -> str:
    return _TYPE_LABELS.get(ptype.lower().replace("_", ""), ptype.replace("_", " ").title())


def _dashboard_url_path(server_name: str) -> str:
    return f"minecraft-{_slug(server_name)}"


# ---------------------------------------------------------------------------
# Card builders
# ---------------------------------------------------------------------------

def _glance_card(title: str, entity_ids: list[str]) -> dict[str, Any]:
    return {
        "type": "glance",
        "title": title,
        "show_name": True,
        "show_state": True,
        "entities": entity_ids,
    }


def _entities_card(title: str, entity_ids: list[str], *, icon: str | None = None) -> dict[str, Any]:
    card: dict[str, Any] = {
        "type": "entities",
        "title": title,
        "entities": entity_ids,
    }
    if icon:
        card["icon"] = icon
    return card


def _gauge_card(title: str, entity_id: str) -> dict[str, Any]:
    return {
        "type": "gauge",
        "title": title,
        "entity": entity_id,
        "min": 0,
        "max": 100,
        "severity": {"green": 50, "yellow": 20, "red": 0},
    }


def _markdown_card(content: str) -> dict[str, Any]:
    return {"type": "markdown", "content": content}


# ---------------------------------------------------------------------------
# Dashboard config builder
# ---------------------------------------------------------------------------

def _build_dashboard_config(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Build the full Lovelace config dict for this server entry."""
    server_name = entry.data[CONF_SERVER_NAME]
    entry_id = entry.entry_id
    sensors = hass.data[DOMAIN][DATA_SENSORS].get(entry_id, {})
    entity_reg = er.async_get(hass)

    # --- helpers -----------------------------------------------------------

    def _eid(sensor_key: str) -> str | None:
        """Look up the live entity_id for a sensor key via the entity registry."""
        sensor_info = sensors.get(sensor_key, {})
        platform = (
            "binary_sensor"
            if sensor_info.get("type") == SENSOR_TYPE_BOOLEAN
            else "sensor"
        )
        return entity_reg.async_get_entity_id(platform, DOMAIN, f"{DOMAIN}_{entry_id}_{sensor_key}")

    def _eids(sensor_keys: list[str]) -> list[str]:
        return [e for e in (_eid(k) for k in sensor_keys) if e]

    # --- group sensors: computer_id → device_id → [keys] ------------------
    structure: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for sensor_key, info in sensors.items():
        cid = info.get("computer_id", "default")
        did = info.get("device_id", f"{entry_id}_{cid}")
        structure[cid][did].append(sensor_key)

    # --- build cards -------------------------------------------------------
    all_cards: list[dict[str, Any]] = []

    if not sensors:
        all_cards.append(_markdown_card(
            f"## Minecraft — {server_name}\n\n"
            "No data received yet.\n\n"
            "Start your CC: Tweaked scanner and make sure it is pointed at this "
            "webhook URL.  Once the first scan arrives, run **Settings → "
            f"Devices & Services → Minecraft Webhook → {server_name} → "
            "Regenerate Dashboard** to populate this view."
        ))
        return {"views": [{"title": server_name, "path": "default",
                           "icon": "mdi:minecraft", "cards": all_cards}]}

    for cid in sorted(structure):
        device_map = structure[cid]
        computer_device_id = f"{entry_id}_{cid}"
        computer_label = cid.replace("_", " ").title()

        # Markdown heading for this computer
        all_cards.append(_markdown_card(f"## {computer_label}"))

        # Computer-level status fields
        prefix = f"{cid}_" if cid != "default" else ""
        status_candidates = [
            f"{prefix}online", f"{prefix}label",
            f"{prefix}uptime", f"{prefix}periph_count",
        ]
        status_eids = _eids([k for k in status_candidates if k in sensors])
        if status_eids:
            all_cards.append(_glance_card(f"{computer_label} — Status", status_eids))

        # Turtle info (if this is a turtle computer)
        turtle_keys = [k for k in device_map.get(computer_device_id, [])
                       if "turtle" in k]
        turtle_eids = _eids(turtle_keys)
        if turtle_eids:
            all_cards.append(_entities_card("Turtle", turtle_eids, icon="mdi:robot"))

        # Per-peripheral sections
        for did in sorted(device_map):
            if did == computer_device_id:
                continue  # already handled above

            # Extract periph name from device_id
            computer_prefix = f"{computer_device_id}_"
            if not did.startswith(computer_prefix):
                continue
            periph_name = did[len(computer_prefix):]
            periph_label = periph_name.replace("_", " ").title()

            keys = device_map[did]

            # Find peripheral type from *_type sensor
            type_key = f"{prefix}{periph_name}_type"
            periph_type_val = sensors.get(type_key, {}).get("value", "")
            type_lbl = _type_label(periph_type_val) if periph_type_val else periph_label
            section_title = f"{periph_label} — {type_lbl}"

            # Separate keys into pct/type/other
            pct_keys   = [k for k in keys if k.endswith("_percent") or k.endswith("_pct")]
            type_keys  = [k for k in keys if k.endswith("_type")]
            other_keys = [k for k in keys if k not in pct_keys and k not in type_keys]

            # Gauge for first percent field
            if pct_keys:
                gauge_eid = _eid(pct_keys[0])
                if gauge_eid:
                    all_cards.append(_gauge_card(section_title, gauge_eid))

            # Entities card for all remaining fields (include pct so exact number is visible)
            detail_keys = pct_keys + other_keys
            detail_eids = _eids(detail_keys)
            if detail_eids:
                all_cards.append(_entities_card(section_title, detail_eids))

    return {
        "views": [{
            "title": server_name,
            "path": "default",
            "icon": "mdi:minecraft",
            "cards": all_cards,
        }]
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def async_setup_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register the sidebar dashboard and write an initial (possibly empty) config.

    A second regeneration is scheduled after _AUTO_REGEN_DELAY seconds so that
    the dashboard fills in automatically once the first scan arrives.
    """
    server_name = entry.data[CONF_SERVER_NAME]
    url_path = _dashboard_url_path(server_name)
    title = f"Minecraft — {server_name}"

    # Register the dashboard entry in Lovelace
    lovelace = hass.data.get("lovelace")
    if lovelace and hasattr(lovelace, "dashboards"):
        dashboards = lovelace.dashboards
        existing_paths = {item.get("url_path") for item in dashboards.async_items()}
        if url_path not in existing_paths:
            try:
                await dashboards.async_create_item({
                    "require_admin": False,
                    "show_in_sidebar": True,
                    "icon": "mdi:minecraft",
                    "title": title,
                    "mode": "storage",
                    "url_path": url_path,
                })
                _LOGGER.info("Created Lovelace dashboard '/%s'", url_path)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.warning(
                    "Could not register dashboard '/%s': %s — "
                    "restart HA after setup to make it appear in the sidebar.",
                    url_path, exc,
                )
    else:
        _LOGGER.warning(
            "Lovelace component not available — dashboard '/%s' was not registered. "
            "Restart HA to trigger registration.",
            url_path,
        )

    # Write initial config (may be mostly empty until first scan)
    await async_regenerate_dashboard(hass, entry)

    # Schedule an automatic regeneration so the dashboard fills in once
    # the first scan has arrived and sensors have been registered.
    async_call_later(
        hass,
        _AUTO_REGEN_DELAY,
        lambda _: hass.async_create_task(async_regenerate_dashboard(hass, entry)),
    )


async def async_regenerate_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Rebuild the dashboard config from current sensors and save it to storage.

    Safe to call at any time.  The next time a browser navigates to the
    dashboard it will show the updated content without an HA restart.
    """
    server_name = entry.data[CONF_SERVER_NAME]
    url_path = _dashboard_url_path(server_name)

    config = _build_dashboard_config(hass, entry)

    store = Store(
        hass,
        _STORAGE_VERSION,
        f"lovelace.{url_path}",
        minor_version=_STORAGE_MINOR_VERSION,
        atomic_writes=True,
    )
    await store.async_save({"config": config})
    _LOGGER.info(
        "Dashboard for '%s' regenerated (%d card(s))",
        server_name,
        sum(len(v.get("cards", [])) for v in config.get("views", [])),
    )


async def async_remove_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove the dashboard when the integration entry is unloaded."""
    server_name = entry.data[CONF_SERVER_NAME]
    url_path = _dashboard_url_path(server_name)

    lovelace = hass.data.get("lovelace")
    if lovelace and hasattr(lovelace, "dashboards"):
        dashboards = lovelace.dashboards
        for item in list(dashboards.async_items()):
            if item.get("url_path") == url_path:
                try:
                    await dashboards.async_delete_item(item["id"])
                    _LOGGER.info("Removed Lovelace dashboard '/%s'", url_path)
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.warning("Could not remove dashboard '/%s': %s", url_path, exc)
                break

    # Clear the storage file too
    store = Store(hass, _STORAGE_VERSION, f"lovelace.{url_path}",
                  minor_version=_STORAGE_MINOR_VERSION)
    await store.async_remove()

