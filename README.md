# Minecraft Webhook Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/tyler919/minecraft-ha)](https://github.com/tyler919/minecraft-ha/releases)
[![License](https://img.shields.io/github/license/tyler919/minecraft-ha)](LICENSE)

Receive real-time data from your Minecraft Java Edition server via webhooks. Supports multiple servers with automatic sensor discovery!

## Features

- **Webhook-Based** - Your Minecraft mod/plugin sends data to Home Assistant
- **Auto-Discovery** - Sensors are automatically created from incoming JSON data
- **Multi-Server Support** - Monitor multiple Minecraft servers
- **Dynamic Sensors** - Any data sent becomes a sensor automatically
- **Binary Sensors** - Boolean values automatically become binary sensors
- **Smart Icons** - Automatic icon assignment based on data type

## How It Works

1. Set up the integration in Home Assistant (you'll get a webhook URL)
2. Configure your Minecraft mod to send JSON data to the webhook URL
3. Sensors are automatically created based on the data received

```
Minecraft Server → Mod sends JSON → Home Assistant Webhook → Auto-created Sensors
```

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots in the top right corner
3. Select "Custom repositories"
4. Add this repository URL: `https://github.com/tyler919/minecraft-ha`
5. Select "Integration" as the category
6. Click "Add"
7. Search for "Minecraft Webhook" and install
8. Restart Home Assistant

### Manual Installation

1. Download the latest release from GitHub
2. Copy the `custom_components/minecraft_webhook` folder to your Home Assistant's `custom_components` directory
3. Restart Home Assistant

## Configuration

### Adding a Server

1. Go to **Settings > Devices & Services > Add Integration**
2. Search for "Minecraft Webhook"
3. Enter a name for your server (e.g., "Survival", "Creative")
4. Click Submit

### Getting the Webhook URL

After adding a server:
1. Go to **Settings > Devices & Services > Minecraft Webhook**
2. Click **Configure** on your server
3. Copy the webhook URL shown

The webhook URL format is:
```
http://your-ha-instance:8123/api/webhook/[webhook_id]
```

## Sending Data from Minecraft

Your Minecraft mod should send HTTP POST requests with JSON data to the webhook URL.

### Example JSON Payloads

#### Basic Server Info
```json
{
  "online": true,
  "players": 5,
  "max_players": 20,
  "tps": 19.8,
  "version": "1.20.4"
}
```

#### Player List
```json
{
  "player_count": 3,
  "players": ["Steve", "Alex", "Notch"],
  "online": true
}
```

#### Detailed Server Stats
```json
{
  "server": {
    "online": true,
    "tps": 20.0,
    "mspt": 45.2,
    "memory_used": 2048,
    "memory_max": 4096,
    "uptime": 86400
  },
  "world": {
    "time": 6000,
    "day": 142,
    "weather": "clear",
    "difficulty": "hard"
  },
  "players": {
    "online": 5,
    "max": 20,
    "list": ["Steve", "Alex"]
  }
}
```

#### Player Statistics
```json
{
  "player": "Steve",
  "health": 20,
  "food": 18,
  "level": 30,
  "experience": 1250,
  "dimension": "overworld",
  "x": 100,
  "y": 64,
  "z": -200,
  "gamemode": "survival"
}
```

### Nested Data

Nested JSON objects are automatically flattened with underscores:
```json
{"server": {"tps": 20}}
```
Becomes sensor: `sensor.minecraft_[server_name]_server_tps`

### Lists

Lists are stored with their count as the state and items as an attribute:
```json
{"players": ["Steve", "Alex"]}
```
Creates sensor with state `2` and attribute `items: ["Steve", "Alex"]`

## Auto-Created Sensors

Sensors are automatically created based on the JSON keys you send:

| JSON Key | Sensor Type | Example Entity ID |
|----------|-------------|-------------------|
| `players` (number) | Sensor | `sensor.minecraft_survival_players` |
| `online` (boolean) | Binary Sensor | `binary_sensor.minecraft_survival_online` |
| `tps` (number) | Sensor | `sensor.minecraft_survival_tps` |
| `players` (list) | Sensor (count) | `sensor.minecraft_survival_players` |

## Smart Icons

The integration automatically assigns appropriate icons based on common Minecraft data:

| Data Type | Icon |
|-----------|------|
| players, player_count | mdi:account-group |
| tps | mdi:speedometer |
| health | mdi:heart |
| deaths | mdi:skull-crossbones |
| weather | mdi:weather-cloudy |
| dimension | mdi:map-marker |
| ... and more! | |

## Example Automations

### Notify When Server Goes Offline
```yaml
automation:
  - alias: "Minecraft Server Offline Alert"
    trigger:
      - platform: state
        entity_id: binary_sensor.minecraft_survival_online
        to: "off"
    action:
      - service: notify.mobile_app
        data:
          title: "Minecraft Server Down!"
          message: "Your Survival server has gone offline."
```

### Player Join Notification
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
          message: "A player joined! Now {{ states('sensor.minecraft_survival_player_count') }} online."
```

## Troubleshooting

### Sensors Not Appearing
1. Check Home Assistant logs for errors
2. Verify the webhook URL is correct
3. Make sure your mod is sending valid JSON
4. Check the content-type header is `application/json`

### Testing the Webhook
You can test with curl:
```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"players": 5, "online": true, "tps": 20.0}' \
  http://your-ha:8123/api/webhook/your_webhook_id
```

### Debug Logging
Add to your `configuration.yaml`:
```yaml
logger:
  default: info
  logs:
    custom_components.minecraft_webhook: debug
```

## Creating a Minecraft Mod

To send data from your Minecraft server, you'll need a mod (Forge/Fabric) or plugin (Spigot/Paper) that makes HTTP requests.

### Basic Fabric/Forge Mod Approach
```java
// Pseudocode - actual implementation depends on your mod loader
HttpClient client = HttpClient.newHttpClient();

JsonObject data = new JsonObject();
data.addProperty("players", server.getPlayerCount());
data.addProperty("tps", server.getTPS());
data.addProperty("online", true);

HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create("http://your-ha:8123/api/webhook/your_id"))
    .header("Content-Type", "application/json")
    .POST(HttpRequest.BodyPublishers.ofString(data.toString()))
    .build();

client.sendAsync(request, HttpResponse.BodyHandlers.ofString());
```

## Contributing

Issues and pull requests are welcome! Please report bugs at [GitHub Issues](https://github.com/tyler919/minecraft-ha/issues).

## License

MIT License - see [LICENSE](LICENSE) for details.

---

**Happy Mining!** ⛏️
