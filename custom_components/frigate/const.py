"""Constants for frigate."""
# Base component constants
NAME = "Frigate"
DOMAIN = "frigate"
DOMAIN_DATA = f"{DOMAIN}_data"
VERSION = "0.0.1"
ISSUE_URL = "https://github.com/blakeblackshear/frigate-hass-integration/issues"

# Icons
ICON_CAR = "mdi:shield-car"
ICON_CAT = "mdi:cat"
ICON_DOG = "mdi:dog-side"
ICON_FILM_MULTIPLE = "mdi:filmstrip-box-multiple"
ICON_IMAGE_MULTIPLE = "mdi:image-multiple"
ICON_MOTION_SENSOR = "hass:motion-sensor"
ICON_OTHER = "mdi:shield-alert"
ICON_PERSON = "mdi:shield-account"
ICON_SPEEDOMETER = "mdi:speedometer"

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
DEFAULT_HOST = "http://ccab4aaf-frigate:5000"


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
