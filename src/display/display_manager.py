import fnmatch
import logging

from utils.image_utils import resize_image, change_orientation, apply_image_enhancement
from display.mock_display import MockDisplay

logger = logging.getLogger(__name__)

# Try to import hardware displays, but don't fail if they're not available
try:
    from display.inky_display import InkyDisplay
except ImportError:
    logger.info("Inky display not available, hardware support disabled")

try:
    from display.waveshare_display import WaveshareDisplay
except ImportError:
    logger.info("Waveshare display not available, hardware support disabled")


class DisplayManager:
    """Manages the display and rendering of images."""

    def __init__(self, device_config, epd_display):
        self.device_config = device_config
        self.display = epd_display

        display_type = device_config.get_config("display_type", default="inky")

        if display_type == "mock":
            self.display = MockDisplay(device_config)
        elif display_type == "inky":
            self.display = InkyDisplay(device_config)
        elif fnmatch.fnmatch(display_type, "epd*in*"):
            # Waveshare e-paper family
            self.display = WaveshareDisplay(device_config)
        else:
            raise ValueError(f"Unsupported display type: {display_type}")

    def display_image(self, image, image_settings=None):
        # Resolve settings with safe fallbacks
        settings = (
            image_settings
            if isinstance(image_settings, dict)
            else (self.device_config.get_config("image_settings", {}) or {})
        )

        # Orientation (optional)
        orientation = self.device_config.get_config("orientation", None)
        if orientation:
            image = change_orientation(image, orientation)

        # Resize to panel
        image = resize_image(image, self.device_config.get_resolution())

        # Invert/rotate 180 if configured
        if self.device_config.get_config("inverted_image", False):
            image = image.rotate(180)

        # Enhance AFTER resize so sharpening/contrast apply to final size
        image = apply_image_enhancement(image, settings)

        # Ensure display exists
        if not hasattr(self, "display"):
            raise ValueError("No valid display instance initialized.")

        # Save last-shown image (for restore on wake)
        logger.info("Saving image to %s",
                    self.device_config.current_image_file)
        image.save(self.device_config.current_image_file)

        # Hand off to the concrete driver; support a few common APIs
        try:
            if hasattr(self.display, "display_image"):
                self.display.display_image(image, settings)
            elif hasattr(self.display, "display"):
                self.display.display(image)
            elif hasattr(self.display, "draw"):
                self.display.draw(image)
                if hasattr(self.display, "refresh"):
                    self.display.refresh()
            else:
                raise AttributeError(
                    "Display driver exposes no known draw method")
        except Exception as e:
            logger.exception("Failed to push image to display: %s", e)

        return image
