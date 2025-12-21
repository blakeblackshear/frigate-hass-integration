"""Handles icons for different entity types."""

ICON_AUDIO = "mdi:ear-hearing"
ICON_AUDIO_OFF = "mdi:ear-hearing-off"
ICON_PTZ_AUTOTRACKER = "mdi:cctv"
ICON_DESCRIPTIONS = "mdi:text-box-check"
ICON_BICYCLE = "mdi:bicycle"
ICON_CAR = "mdi:car"
ICON_CAT = "mdi:cat"
ICON_CONTRAST = "mdi:contrast-circle"
ICON_CORAL = "mdi:scoreboard-outline"
ICON_COW = "mdi:cow"
ICON_DOG = "mdi:dog-side"
ICON_FACE = "mdi:face-recognition"
ICON_FILM_MULTIPLE = "mdi:filmstrip-box-multiple"
ICON_HORSE = "mdi:horse"
ICON_IMAGE_MULTIPLE = "mdi:image-multiple"
ICON_LICENSE_PLATE = "mdi:barcode-scan"
ICON_MOTION_SENSOR = "mdi:motion-sensor"
ICON_MOTORCYCLE = "mdi:motorbike"
ICON_OTHER = "mdi:shield-alert"
ICON_PERSON = "mdi:human"
ICON_SERVER = "mdi:server"
ICON_SPEEDOMETER = "mdi:speedometer"
ICON_WAVEFORM = "mdi:waveform"
ICON_UPTIME = "mdi:clock-time-five"

ICON_DEFAULT_ON = "mdi:home"
ICON_REVIEW_ALERTS = "mdi:bell-alert"
ICON_REVIEW_DETECTIONS = "mdi:eye-check"

ICON_CAR_OFF = "mdi:car-off"
ICON_DEFAULT_OFF = "mdi:home-outline"
ICON_DOG_OFF = "mdi:dog-side-off"


def get_dynamic_icon_from_type(obj_type: str, is_on: bool) -> str:
    """Get icon for a specific object type and current state."""

    if obj_type == "car":
        return ICON_CAR if is_on else ICON_CAR_OFF
    if obj_type == "dog":
        return ICON_DOG if is_on else ICON_DOG_OFF
    if obj_type == "sound":
        return ICON_AUDIO if is_on else ICON_AUDIO_OFF

    return ICON_DEFAULT_ON if is_on else ICON_DEFAULT_OFF


def get_icon_from_switch(switch_type: str) -> str:
    """Get icon for a specific switch type."""
    if switch_type == "snapshots":
        return ICON_IMAGE_MULTIPLE
    if switch_type == "recordings":
        return ICON_FILM_MULTIPLE
    if switch_type == "improve_contrast":
        return ICON_CONTRAST
    if switch_type == "audio":
        return ICON_AUDIO
    if switch_type == "ptz_autotracker":
        return ICON_PTZ_AUTOTRACKER
    if switch_type == "object_descriptions" or switch_type == "review_descriptions":
        return ICON_DESCRIPTIONS
    if switch_type == "review_alerts":
        return ICON_REVIEW_ALERTS
    if switch_type == "review_detections":
        return ICON_REVIEW_DETECTIONS

    return ICON_MOTION_SENSOR


def get_icon_from_type(obj_type: str) -> str:
    """Get icon for a specific object type."""

    if obj_type == "person":
        return ICON_PERSON
    if obj_type == "car":
        return ICON_CAR
    if obj_type == "dog":
        return ICON_DOG
    if obj_type == "cat":
        return ICON_CAT
    if obj_type == "motorcycle":
        return ICON_MOTORCYCLE
    if obj_type == "bicycle":
        return ICON_BICYCLE
    if obj_type == "cow":
        return ICON_COW
    if obj_type == "horse":
        return ICON_HORSE

    return ICON_OTHER
