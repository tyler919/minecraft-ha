"""Constants for the Minecraft Webhook integration."""

DOMAIN = "minecraft_webhook"

# GitHub repo for auto error reporting
GITHUB_REPO_OWNER = "tyler919"
GITHUB_REPO_NAME  = "minecraft-ha"

# Configuration
CONF_SERVER_NAME     = "server_name"
CONF_WEBHOOK_ID      = "webhook_id"
CONF_ERROR_REPORTING = "error_reporting"
CONF_GITHUB_TOKEN    = "github_token"

# Data storage keys
DATA_SERVERS = "servers"
DATA_SENSORS = "sensors"
DATA_COORDINATOR = "coordinator"
DATA_COMMANDS = "commands"
DATA_COMPUTERS = "computers"
DATA_CLEANUP_CANCEL = "cleanup_cancel"

# Stale sensor cleanup
STALE_SENSOR_HOURS = 24
PROTECTED_LABEL = "never"

# Pause / ready signalling
READY_DELAY_SECONDS = 30

# Webhook
WEBHOOK_PATH = "/api/webhook/minecraft_{webhook_id}"

# Sensor types (for auto-detection)
SENSOR_TYPE_NUMBER = "number"
SENSOR_TYPE_STRING = "string"
SENSOR_TYPE_BOOLEAN = "boolean"
SENSOR_TYPE_LIST = "list"
SENSOR_TYPE_DICT = "dict"

# Default sensor icons based on common Minecraft data
DEFAULT_ICONS = {
    "players": "mdi:account-group",
    "player_count": "mdi:account-group",
    "online_players": "mdi:account-group",
    "max_players": "mdi:account-multiple",
    "tps": "mdi:speedometer",
    "mspt": "mdi:timer",
    "energy": "mdi:lightning-bolt",
    "max_energy": "mdi:lightning-bolt",
    "energy_rate": "mdi:lightning-bolt-circle",
    "transfer_rate": "mdi:transfer",
    "memory": "mdi:memory",
    "memory_used": "mdi:memory",
    "memory_max": "mdi:memory",
    "uptime": "mdi:clock-outline",
    "world": "mdi:earth",
    "world_time": "mdi:weather-sunset",
    "day": "mdi:calendar-today",
    "weather": "mdi:weather-cloudy",
    "difficulty": "mdi:skull",
    "version": "mdi:minecraft",
    "motd": "mdi:message-text",
    "online": "mdi:server",
    "status": "mdi:server",
    "deaths": "mdi:skull-crossbones",
    "advancements": "mdi:trophy",
    "blocks_broken": "mdi:pickaxe",
    "blocks_placed": "mdi:cube",
    "mobs_killed": "mdi:sword",
    "distance_walked": "mdi:walk",
    "playtime": "mdi:timer-sand",
    "health": "mdi:heart",
    "food": "mdi:food-drumstick",
    "level": "mdi:star",
    "experience": "mdi:star-circle",
    "dimension": "mdi:map-marker",
    "biome": "mdi:tree",
    "x": "mdi:axis-x-arrow",
    "y": "mdi:axis-y-arrow",
    "z": "mdi:axis-z-arrow",
    "seed": "mdi:seed",
    "gamemode": "mdi:controller",
    "chunk": "mdi:grid",
    "entities": "mdi:duck",
    "loaded_chunks": "mdi:grid-large",
}

# Default icon for unknown sensors
DEFAULT_ICON = "mdi:minecraft"

# ── Energy sensor classification ──────────────────────────────────────────────
# Keys containing any of these substrings are treated as power (FE/s → W).
# Checked BEFORE energy keywords because "energy_rate" also contains "energy".
POWER_SENSOR_KEYWORDS = ("energy_rate", "transfer_rate")

# Keys containing "energy" (and not a power keyword or percent) → energy device class.
ENERGY_SENSOR_KEYWORD = "energy"

# 1 FE is treated as 1 Wh, 1 FE/s as 1 W.
# This is the standard community mapping that makes HA's energy dashboard work.
FE_ENERGY_UNIT = "Wh"
FE_POWER_UNIT  = "W"

# Units based on common Minecraft data
DEFAULT_UNITS = {
    "tps": "tps",
    "mspt": "ms",
    "memory": "MB",
    "memory_used": "MB",
    "memory_max": "MB",
    "uptime": "s",
    "health": "HP",
    "food": "points",
    "level": "level",
    "experience": "XP",
    "distance_walked": "blocks",
    "playtime": "s",
    "x": "blocks",
    "y": "blocks",
    "z": "blocks",
}
