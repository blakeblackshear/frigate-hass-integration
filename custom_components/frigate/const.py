"""Constants for frigate."""
# Base component constants
NAME = "Frigate"
DOMAIN = "frigate"
FRIGATE_VERSION_ERROR_CUTOFF = "0.8.4"
FRIGATE_RELEASES_URL = "https://github.com/blakeblackshear/frigate/releases"
FRIGATE_RELEASE_TAG_URL = f"{FRIGATE_RELEASES_URL}/tag"

# Platforms
BINARY_SENSOR = "binary_sensor"
NUMBER = "number"
SENSOR = "sensor"
SWITCH = "switch"
CAMERA = "camera"
UPDATE = "update"
PLATFORMS = [SENSOR, CAMERA, NUMBER, SWITCH, BINARY_SENSOR, UPDATE]

# Device Classes
# This device class does not exist in HA, but we use it to be able
# to filter cameras in selectors
DEVICE_CLASS_CAMERA = "camera"

# Unit of measurement
FPS = "fps"
MS = "ms"

# Attributes
ATTR_CLIENT = "client"
ATTR_CLIENT_ID = "client_id"
ATTR_CONFIG = "config"
ATTR_COORDINATOR = "coordinator"
ATTR_EVENT_ID = "event_id"
ATTR_FAVORITE = "favorite"
ATTR_MQTT = "mqtt"

# Configuration and options
CONF_CAMERA_STATIC_IMAGE_HEIGHT = "camera_image_height"
CONF_MEDIA_BROWSER_ENABLE = "media_browser_enable"
CONF_NOTIFICATION_PROXY_ENABLE = "notification_proxy_enable"
CONF_PASSWORD = "password"
CONF_PATH = "path"
CONF_RTMP_URL_TEMPLATE = "rtmp_url_template"
CONF_RTSP_URL_TEMPLATE = "rtsp_url_template"
CONF_NOTIFICATION_PROXY_EXPIRE_AFTER_SECONDS = "notification_proxy_expire_after_seconds"

# Defaults
DEFAULT_NAME = DOMAIN
DEFAULT_HOST = "http://ccab4aaf-frigate:5000"


STARTUP_MESSAGE = """
-------------------------------------------------------------------
{title}
Integration Version: {integration_version}
This is a custom integration!
If you have any issues with this you need to open an issue here:
https://github.com/blakeblackshear/frigate-hass-integration/issues
-------------------------------------------------------------------
"""

# Min Values
MAX_CONTOUR_AREA = 50
MAX_THRESHOLD = 255

# Min Values
MIN_CONTOUR_AREA = 15
MIN_THRESHOLD = 1

# States
STATE_DETECTED = "active"
STATE_IDLE = "idle"

# Statuses
STATUS_ERROR = "error"
STATUS_RUNNING = "running"
STATUS_STARTING = "starting"

# Frigate Services
SERVICE_FAVORITE_EVENT = "favorite_event"
