# src/display/display_manager.py
import fnmatch
import logging
import time
import threading
from PIL import Image, ImageStat  # <-- add
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


# ---- helper ---------------------------------------------------------------

def _is_solid_black(img: Image.Image) -> bool:
    """Return True if the image is all black (cheap check)."""
    try:
        # Convert to 8-bit luminance and check extrema
        lum = img.convert("L")
        return lum.getextrema() == (0, 0)
    except Exception:
        return False


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

        # Concurrency + state
        self._lock = threading.RLock()
        self._asleep = False

    # ---- Power state --------------------------------------------------------

    def is_asleep(self):
        return self._asleep

    def sleep(self):
        with self._lock:
            self._asleep = True
            if hasattr(self.display, "sleep"):
                try:
                    self.display.sleep()
                except Exception:
                    pass

    def wake(self):
        with self._lock:
            self._asleep = False
            if hasattr(self.display, "wake"):
                try:
                    self.display.wake()
                except Exception:
                    pass

    # ---- Drawing ------------------------------------------------------------

    def display_image(self, image, image_settings=None, save_to_cache=True, force_draw=False):
        """
        Render an image to the panel.
        - save_to_cache: write current_image.png (ignored if asleep)
        - force_draw: draw to hardware even if asleep
        """
        with self._lock:
            # ---- FAST PATH: solid black ----
            if _is_solid_black(image):
                w, h = self.device_config.get_resolution()
                if image.size != (w, h):
                    image = image.resize((w, h))
                save_to_cache = False  # never cache black

                if self._asleep and not force_draw:
                    return image
                if not getattr(self, "display", None):
                    raise ValueError("No valid display instance initialized.")

                try:
                    if hasattr(self.display, "display_image"):
                        self.display.display_image(
                            image, {})  # no enhancements
                    elif hasattr(self.display, "display"):
                        self.display.display(image)
                    elif hasattr(self.display, "draw"):
                        self.display.draw(image)
                        getattr(self.display, "refresh", lambda: None)()
                except Exception as e:
                    logger.exception("Failed to push black frame: %s", e)
                return image

            # ---- NORMAL PATH ------------------------------------------------
            settings = (
                image_settings if isinstance(image_settings, dict)
                else (self.device_config.get_config("image_settings", {}) or {})
            )

            # Transform pipeline
            orientation = self.device_config.get_config("orientation", None)
            if orientation:
                image = change_orientation(image, orientation)

            image = resize_image(image, self.device_config.get_resolution())

            if self.device_config.get_config("inverted_image", False):
                image = image.rotate(180)

            image = apply_image_enhancement(image, settings)

            # Cache only when awake
            if save_to_cache and not self._asleep:
                logger.info("Saving image to %s",
                            self.device_config.current_image_file)
                image.save(self.device_config.current_image_file)

            # Skip drawing while asleep unless forced
            if self._asleep and not force_draw:
                logger.debug("Display asleep: skipping hardware draw")
                return image

            if not getattr(self, "display", None):
                raise ValueError("No valid display instance initialized.")

            # Push to hardware
            try:
                if hasattr(self.display, "display_image"):
                    self.display.display_image(image, settings)
                elif hasattr(self.display, "display"):
                    self.display.display(image)
                elif hasattr(self.display, "draw"):
                    self.display.draw(image)
                    getattr(self.display, "refresh", lambda: None)()
            except Exception as e:
                logger.exception("Failed to push image to display: %s", e)

            return image

    # ---- Panel utilities ----------------------------------------------------

    def wait_until_idle(self):
        """Block until the panel is ready (best-effort; falls back to a delay)."""
        d = self.display
        try:
            if hasattr(d, "wait_until_idle"):
                d.wait_until_idle()
                return
            epd = getattr(d, "epd", None)
            if epd and hasattr(epd, "ReadBusy"):
                epd.ReadBusy()
                return
        except Exception:
            pass
        time.sleep(3)  # conservative full-refresh delay

    def clear_panel(self, to_white=True):
        """Send a full-panel clear to reduce banding/ghosting."""
        with self._lock:
            d = self.display
            try:
                if hasattr(d, "clear"):
                    d.clear("white" if to_white else "black")
                    return
                if hasattr(d, "Clear"):
                    d.Clear(0xFF if to_white else 0x00)
                    return
            except Exception:
                logger.exception("Panel clear failed")
