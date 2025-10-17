# src/display/display_manager.py
import fnmatch
import logging
from utils.image_utils import resize_image, change_orientation, apply_image_enhancement
from display.mock_display import MockDisplay

logger = logging.getLogger(__name__)

try:
    from display.inky_display import InkyDisplay
except ImportError:
    InkyDisplay = None
    logger.info("Inky display not available, hardware support disabled")

try:
    from display.waveshare_display import WaveshareDisplay
except ImportError:
    WaveshareDisplay = None
    logger.info("Waveshare display not available, hardware support disabled")


class DisplayManager:
    """Manages the display and rendering of images."""

    def __init__(self, device_config, epd_display=None):
        self.device_config = device_config
        self.display = epd_display  # may be None

        display_type = device_config.get_config("display_type", "inky")

        if self.display is None:
            if display_type == "mock":
                self.display = MockDisplay(device_config)
            elif display_type == "inky":
                if InkyDisplay is None:
                    raise ValueError("InkyDisplay not available")
                self.display = InkyDisplay(device_config)
            elif fnmatch.fnmatch(display_type, "epd*in*"):
                if WaveshareDisplay is None:
                    raise ValueError("WaveshareDisplay not available")
                self.display = WaveshareDisplay(device_config)
            else:
                raise ValueError(f"Unsupported display type: {display_type}")
        
        self._asleep = False

    def is_asleep(self):
        return self._asleep

    def sleep(self):
        self._asleep = True
        if hasattr(self.display, "sleep"):
            try: self.display.sleep()
            except Exception: pass

    def wake(self):
        self._asleep = False
        if hasattr(self.display, "wake"):
            try: self.display.wake()
            except Exception: pass

    def display_image(self, image, image_settings=None, save_to_cache=True):
        settings = (
            image_settings if isinstance(image_settings, dict)
            else (self.device_config.get_config("image_settings", {}) or {})
        )

        orientation = self.device_config.get_config("orientation", None)
        if orientation:
            image = change_orientation(image, orientation)

        image = resize_image(image, self.device_config.get_resolution())

        if self.device_config.get_config("inverted_image", False):
            image = image.rotate(180)

        # Enhance AFTER resize
        image = apply_image_enhancement(image, settings)

        if not hasattr(self, "display"):
            raise ValueError("No valid display instance initialized.")

        # ⬇️ Only persist if asked to
        # 👇 skip cache writes while asleep
        if save_to_cache and not self._asleep:
            logger.info("Saving image to %s", self.device_config.current_image_file)
            image.save(self.device_config.current_image_file)

        # 👇 skip pushing to hardware while asleep unless explicitly forced
        if self._asleep and not force_draw:
            logger.debug("Display asleep: skipping hardware draw")
            return image


        # Hand off to the driver
        if hasattr(self.display, "display_image"):
            self.display.display_image(image, settings)
        elif hasattr(self.display, "display"):
            self.display.display(image)
        elif hasattr(self.display, "draw"):
            self.display.draw(image)
            getattr(self.display, "refresh", lambda: None)()

        return image
