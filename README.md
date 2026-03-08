# Minecraft Webhook Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/tyler919/minecraft-ha)](https://github.com/tyler919/minecraft-ha/releases)
[![License](https://img.shields.io/github/license/tyler919/minecraft-ha)](LICENSE)

Receive real-time data from your Minecraft world in Home Assistant — energy levels, storage contents, player detection, environment readings, and more — automatically turned into sensors and binary sensors.

---

## Designed for CC: Tweaked

This integration was built from the ground up to work alongside **[CC: Tweaked](https://modrinth.com/mod/cc-tweaked)** (also known as ComputerCraft), a Minecraft mod that adds programmable computers to the game.

The companion Lua scripts — **[minecraft-ha-cc](https://github.com/tyler919/minecraft-ha-cc)** — run directly on CC: Tweaked computers inside your Minecraft world. They scan connected peripherals (energy cells, ME systems, storage, players, environment, and more) and POST that data to this integration automatically, on a configurable interval.

```
In-game CC: Tweaked Computer
        │
        │  HTTP POST (JSON)
        ▼
Home Assistant Webhook
        │
        │  Auto-discovery
        ▼
Sensors & Binary Sensors
```

The two repos are designed as a matched pair:

| Repo | What it is |
|---|---|
| [`minecraft-ha`](https://github.com/tyler919/minecraft-ha) | This repo — the HA custom integration |
| [`minecraft-ha-cc`](https://github.com/tyler919/minecraft-ha-cc) | The Lua scripts that run on CC: Tweaked computers in-game |

### Can I use this without CC: Tweaked?

Yes. The integration is a standard HA webhook receiver — it accepts any HTTP POST with a JSON body. If you have a different mod, plugin, or external system that can make HTTP requests, it will work fine. CC: Tweaked is simply the primary supported client and the one these two repos were built around.

---

## Features

- **Webhook-based** — no persistent connection required; the computer posts data and moves on
- **Auto-discovery** — every JSON key becomes a sensor automatically, no configuration needed
- **Multi-server support** — add as many Minecraft servers as you like, each gets its own webhook
- **Bidirectional** — HA can send commands back to in-game computers via the same webhook
- **Energy dashboard support** — Forge Energy (FE) values mapped to Wh/W so they appear in the HA energy dashboard
- **Binary sensors** — boolean values (online, raining, etc.) become binary sensors automatically
- **Stale sensor cleanup** — sensors that haven't reported in 24 hours are removed automatically (label a sensor `never` to protect it)
- **Pause/ready handshake** — when the integration restarts, it signals computers to pause and resumes them when ready
- **Auto error reporting** — optional: crashes in the integration automatically open a GitHub issue (requires a GitHub token)

---

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots → **Custom repositories**
3. Add `https://github.com/tyler919/minecraft-ha` as an **Integration**
4. Search for **Minecraft Webhook** and install
5. Restart Home Assistant

### Manual

1. Download the latest release
2. Copy `custom_components/minecraft_webhook` into your HA `custom_components` directory
3. Restart Home Assistant

---

## Setup

### 1. Add the integration

**Settings → Devices & Services → Add Integration → Minecraft Webhook**

Enter a name for your server (e.g. `Survival`). The integration creates a webhook and registers it.

### 2. Get your webhook URL

**Settings → Devices & Services → Minecraft Webhook → Configure**

Copy the URL shown. It looks like:
```
http://your-ha-ip:8123/api/webhook/minecraft_xxxxxxxxxxxx
```

### 3. Point your client at it

**If using CC: Tweaked**, install the companion scripts from [`minecraft-ha-cc`](https://github.com/tyler919/minecraft-ha-cc) and paste the webhook URL into the setup wizard. Everything else is automatic.

**If using a custom client**, POST JSON to the webhook URL — see the payload format below.

---

## Webhook Payload Format

POST JSON to your webhook URL with `Content-Type: application/json`.

### Minimal example
```json
{
  "computer_id": "my_computer",
  "online": true,
  "players": 3,
  "tps": 19.8
}
```

### Nested data (auto-flattened)
```json
{
  "computer_id": "scanner_1",
  "left_energy": 750000,
  "left_max_energy": 1000000,
  "left_percent": 75
}
```
Nested objects are flattened with underscores: `{"server": {"tps": 20}}` → sensor `server_tps`.

### Response format
The webhook returns JSON containing any pending commands queued from HA:
```json
{
  "status": "ok",
  "commands": [
    {"command": "reboot", "data": {}}
  ],
  "outputs": {}
}
```

---

## Sensor Auto-Discovery

Every key in the JSON payload becomes a sensor. Types are detected automatically:

| JSON value type | HA entity |
|---|---|
| `true` / `false` | `binary_sensor` |
| Number (int/float) | `sensor` with `state_class: measurement` |
| String | `sensor` |
| List | `sensor` (state = count, items in attributes) |

### Energy sensors
Fields containing `energy` (e.g. `left_energy`, `max_energy`) are automatically given:
- `device_class: energy`, `unit: Wh` — compatible with the HA energy dashboard (1 FE = 1 Wh)

Fields containing `energy_rate` or `transfer_rate` get:
- `device_class: power`, `unit: W`

---

## HA Services

Three services are available under the `minecraft_webhook` domain:

### `minecraft_webhook.send_command`
Queue a command for an in-game computer to receive on its next poll.

| Field | Required | Description |
|---|---|---|
| `server` | Yes | Server name as set during setup |
| `computer_id` | Yes | The `computer_id` the CC computer sends |
| `command` | Yes | Command string (e.g. `reboot`, `setup`, `scan_now`) |
| `data` | No | Optional extra data object |

### `minecraft_webhook.set_output`
Store a named value for a CC computer to read back.

| Field | Required | Description |
|---|---|---|
| `server` | Yes | Server name |
| `computer_id` | Yes | Computer ID |
| `output_name` | Yes | Key name the computer will read |
| `value` | Yes | The value to store |

### `minecraft_webhook.clear_commands`
Clear the pending command queue for a computer or an entire server.

---

## Stale Sensor Cleanup

Sensors that haven't received data in **24 hours** are automatically deleted. This keeps your HA instance clean if you move or remove computers in-game.

To permanently protect a sensor from deletion, add the label **`never`** to it in the HA entity registry.

---

## Auto Error Reporting (Optional)

The integration can automatically open a GitHub issue on this repo when it encounters an unexpected error.

To enable:
1. **Settings → Devices & Services → Minecraft Webhook → Configure**
2. Toggle **Error Reporting** on
3. Paste a GitHub Personal Access Token (needs `public_repo` scope)

Features:
- Issues are deduplicated by error hash — the same crash won't create duplicate issues
- Rate limited to one issue per error type per hour
- Issues are labelled `auto-reported` + `bug`
- Completely opt-in; disabled by default

---

## Example Automations

### Alert when a server stops reporting
```yaml
automation:
  - alias: "Minecraft Server Offline Alert"
    trigger:
      - platform: state
        entity_id: binary_sensor.minecraft_survival_online
        to: "off"
        for: "00:02:00"
    action:
      - service: notify.mobile_app
        data:
          title: "Minecraft Server Down"
          message: "Survival server hasn't reported in 2 minutes."
```

### Notify when a player joins
```yaml
automation:
  - alias: "Player Joined Minecraft"
    trigger:
      - platform: state
        entity_id: sensor.minecraft_survival_player_count
    condition:
      - condition: template
        value_template: "{{ trigger.to_state.state | int > trigger.from_state.state | int }}"
    action:
      - service: notify.mobile_app
        data:
          message: "Someone joined! {{ states('sensor.minecraft_survival_player_count') }} online."
```

### Low energy warning
```yaml
automation:
  - alias: "Minecraft Low Energy Warning"
    trigger:
      - platform: numeric_state
        entity_id: sensor.minecraft_survival_left_percent
        below: 10
    action:
      - service: notify.mobile_app
        data:
          message: "Warning: Energy storage is below 10%!"
```

---

## Troubleshooting

### Sensors not appearing
1. Check HA logs for errors (`custom_components.minecraft_webhook`)
2. Confirm the webhook URL is correct and the CC computer can reach your HA instance
3. Make sure the POST body is valid JSON with `Content-Type: application/json`

### Testing the webhook manually
```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"computer_id": "test", "online": true, "players": 2}' \
  http://your-ha-ip:8123/api/webhook/minecraft_your_id
```

### Enable debug logging
```yaml
# configuration.yaml
logger:
  default: info
  logs:
    custom_components.minecraft_webhook: debug
```

---

## Related

- **[minecraft-ha-cc](https://github.com/tyler919/minecraft-ha-cc)** — CC: Tweaked Lua scripts that pair with this integration
- **[CC: Tweaked](https://modrinth.com/mod/cc-tweaked)** — the Minecraft mod this integration is built around
- **[Advanced Peripherals](https://modrinth.com/mod/advanced-peripherals)** — recommended companion mod for energy, ME, environment, and player detection peripherals

---

## Contributing

Bug reports and pull requests are welcome. Please use [GitHub Issues](https://github.com/tyler919/minecraft-ha/issues).

## License

MIT — see [LICENSE](LICENSE) for details.
