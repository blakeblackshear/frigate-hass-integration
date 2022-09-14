"""Handles icons for different entity types."""

ICON_BICYCLE = "mdi:bicycle"
ICON_CAR = "mdi:car"
ICON_CAT = "mdi:cat"
ICON_CONTRAST = "mdi:contrast-circle"
ICON_CORAL = "mdi:scoreboard-outline"
ICON_COW = "mdi:cow"
ICON_DOG = "mdi:dog-side"
ICON_FILM_MULTIPLE = "mdi:filmstrip-box-multiple"
ICON_HORSE = "mdi:horse"
ICON_IMAGE_MULTIPLE = "mdi:image-multiple"
ICON_MOTION_SENSOR = "hass:motion-sensor"
ICON_MOTORCYCLE = "mdi:motorbike"
ICON_OTHER = "mdi:shield-alert"
ICON_PERSON = "mdi:human"
ICON_SERVER = "mdi:server"
ICON_SPEEDOMETER = "mdi:speedometer"

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
