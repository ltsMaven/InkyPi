# src/hw/gpio_inputs.py
import os
import threading
import time
import logging
from PIL import Image
from gpiozero import Button, MotionSensor
import inspect

logger = logging.getLogger(__name__)


class GpioInputManager(threading.Thread):
    """
    Listens to:
      - Button on GPIO23: toggle display off/on.
      - PIR on GPIO16: if display is off, wake and restore last image.
    """

    def __init__(self, display_manager, device_config, current_image_path):
        super().__init__(daemon=True)
        self.display_manager = display_manager
        self.device_config = device_config
        self.current_image_path = current_image_path
        self._lock = threading.Lock()

        # Logging + state
        self.logger = logger
        self._is_asleep = False  # make sure this exists before handlers run

        # Inputs (BCM numbering)
        self.button = Button(23, pull_up=True, bounce_time=0.05)
        self.pir = MotionSensor(16)

        # Bind events (press -> sleep/black, release -> wake/restore)
        self.button.when_pressed = self._toggle_power
        # self.button.when_released = None
        self.pir.when_motion = self._on_motion

    # --- Helpers ---
    def _panel_size(self):
        # Support both new and legacy config APIs
        get_res = getattr(self.device_config, "get_resolution", None)
        if callable(get_res):
            w, h = get_res()
        else:
            get_dims = getattr(self.device_config,
                               "get_display_dimensions", None)
            if not callable(get_dims):
                raise AttributeError(
                    "device_config must implement get_resolution() "
                    "or get_display_dimensions()"
                )
            w, h = get_dims()
        return int(w), int(h)

    def _toggle_power(self):
        if self._is_asleep:
            self.logger.info("Button: WAKE + restore last image")
            try:
                self.display_manager.wake()
            except Exception:
                pass
            self._restore_previous_image()  # defaults to save_to_cache=True
            self._is_asleep = False
        else:
            self.logger.info("Button: SLEEP (black, no cache write)")
            self._display(self._black_image(),
                          save_to_cache=False)  # <-- now valid
            
            self.logger.info("Gpio._display sig: %s", inspect.signature(self._display))
            try:
                self.display_manager.sleep()
            except Exception:
                pass
            self._is_asleep = True

    def _black_image(self):
        w, h = self._panel_size()
        return Image.new("RGB", (w, h), "black")

    def _display(self, pil_image, save_to_cache=True):
        # Forward the flag to DisplayManager
        self.display_manager.display_image(
            pil_image, save_to_cache=save_to_cache)

    def _restore_previous_image(self):
        path = self.current_image_path
        self.logger.info("Restoring from %s (exists=%s, size=%s bytes)",
                         self.current_image_path,
                         os.path.isfile(self.current_image_path),
                         os.path.getsize(self.current_image_path) if os.path.isfile(self.current_image_path) else 0)

        if os.path.isfile(self.current_image_path):
            try:
                img = Image.open(self.current_image_path).convert("RGB")
                self._display(img)
                return True
            except Exception as e:
                logger.exception(
                    "Failed to load/restore previous image: %s", e)
        # Fallback to white if nothing to restore
        w, h = self._panel_size()
        img = Image.new("RGB", (w, h), "white")
        self._display(img)
        return False

    # --- Events ---
    def _on_button_pressed(self):
        self.logger.info("GPIO23 pressed: turning display OFF (black + sleep)")
        try:
            # ❗ Don't overwrite cached previous image
            self._display(self._black_image(), save_to_cache=False)
            try:
                self.display_manager.sleep()
            except Exception:
                pass
            self._is_asleep = True
        except Exception as e:
            self.logger.exception("Error turning display off: %s", e)

    def _on_button_released(self):
        self.logger.info("GPIO23 released: waking and restoring last image")
        try:
            try:
                self.display_manager.wake()
            except Exception:
                pass
            self._restore_previous_image()
            self._is_asleep = False
        except Exception as e:
            self.logger.exception("Error restoring display: %s", e)

    def _on_motion(self):
        if self._is_asleep:
            self.logger.info("PIR motion: waking and restoring last image")
            try:
                try:
                    self.display_manager.wake()
                except Exception:
                    pass
                self._restore_previous_image()
                self._is_asleep = False
            except Exception as e:
                self.logger.exception("Error handling PIR wake: %s", e)

    def run(self):
        logger.info(
            "GPIO input manager thread started (Button=GPIO23, PIR=GPIO16)")
        while True:
            time.sleep(1)
