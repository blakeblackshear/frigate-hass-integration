"""Constants for frigate."""
# Base component constants
NAME = "Frigate"
DOMAIN = "frigate"
DOMAIN_DATA = f"{DOMAIN}_data"
VERSION = "0.0.1"
ISSUE_URL = "https://github.com/blakeblackshear/frigate-hass-integration/issues"

# Icons
ICON = "mdi:speedometer"
PERSON_ICON = "mdi:shield-account"
CAR_ICON = "mdi:shield-car"
DOG_ICON = "mdi:dog-side"
CAT_ICON = "mdi:cat"
OTHER_ICON = "mdi:shield-alert"

# Platforms
BINARY_SENSOR = "binary_sensor"
SENSOR = "sensor"
SWITCH = "switch"
CAMERA = "camera"
PLATFORMS = [SENSOR, CAMERA, SWITCH, BINARY_SENSOR]

# Unit of measurement
FPS = "fps"
MS = "ms"

# Configuration and options
CONF_ENABLED = "enabled"

# Defaults
DEFAULT_NAME = DOMAIN


STARTUP_MESSAGE = f"""
-------------------------------------------------------------------
{NAME}
Version: {VERSION}
This is a custom integration!
If you have any issues with this you need to open an issue here:
{ISSUE_URL}
-------------------------------------------------------------------
"""

# States
STATE_DETECTED = "active"
STATE_IDLE = "idle"
