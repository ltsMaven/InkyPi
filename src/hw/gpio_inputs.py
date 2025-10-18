# src/hw/gpio_inputs.py
import os
import threading
import time
import logging
from PIL import Image
from gpiozero import Button  # PIR removed to avoid unintended wakes

logger = logging.getLogger(__name__)


class GpioInputManager(threading.Thread):
    """
    Button on GPIO23:
      - On every press: draw a BLACK frame (do NOT save to cache) and sleep the panel.
    """

    def __init__(self, display_manager, device_config, current_image_path):
        super().__init__(daemon=True)
        self.display_manager = display_manager
        self.device_config = device_config
        self.current_image_path = current_image_path

        self.logger = logger
        self._lock = threading.RLock()
        self._is_asleep = False

        # Inputs (BCM numbering)
        self.button = Button(23, pull_up=True, bounce_time=0.10)
        self.button.when_pressed = self._press_black  # release ignored

    # --- helpers -------------------------------------------------------------

    def _panel_size(self):
        """Get (width, height) from Config; supports legacy method name."""
        get_res = getattr(self.device_config, "get_resolution", None)
        if callable(get_res):
            w, h = get_res()
        else:
            get_dims = getattr(self.device_config,
                               "get_display_dimensions", None)
            if not callable(get_dims):
                raise AttributeError(
                    "device_config must implement get_resolution() or get_display_dimensions()"
                )
            w, h = get_dims()
        return int(w), int(h)

    def _black_image(self):
        w, h = self._panel_size()
        # RGB avoids 1-bit mode issues
        return Image.new("RGB", (w, h), "black")

    def _display(self, pil_image, save_to_cache=True):
        # Let DisplayManager handle transforms; don't save when blanking
        self.display_manager.display_image(
            pil_image, save_to_cache=save_to_cache)

    # --- button handler ------------------------------------------------------

    def _press_black(self):
        """Always draw black and sleep (no restore on subsequent presses)."""
        with self._lock:
            try:
                self.logger.info("Button: draw BLACK (no cache write) + sleep")
                # 1) Draw black but DO NOT overwrite current_image.png
                self._display(self._black_image(), save_to_cache=False)

                # 2) Ensure the refresh finished before sleeping
                try:
                    self.display_manager.wait_until_idle()
                except Exception:
                    pass

                # 3) Sleep the panel so background tasks won't redraw
                try:
                    self.display_manager.sleep()
                except Exception:
                    pass

                self._is_asleep = True
            except Exception as e:
                self.logger.exception("Error handling button press: %s", e)

    # --- thread loop ---------------------------------------------------------

    def run(self):
        self.logger.info("GPIO input manager thread started (Button=GPIO23)")
        while True:
            time.sleep(1)
