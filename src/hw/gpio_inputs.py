# src/hw/gpio_inputs.py
import os
import threading
import time
import logging
from PIL import Image
from gpiozero import Button, MotionSensor

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

        # Inputs (BCM numbering)
        self.button = Button(23, pull_up=True, bounce_time=0.05)
        self.pir = MotionSensor(16)  # defaults are fine; tune if needed

        # State: start "on"
        self.display_off = False

        # Bind events
        self.button.when_pressed = self._on_button_pressed
        self.pir.when_motion = self._on_motion

    # --- Helpers ---
    def _panel_size(self):
        w, h = self.device_config.get_resolution()
        return int(w), int(h)

    def _black_image(self):
        w, h = self._panel_size()
        # mode '1' (1-bit): 0=black, 1=white
        return Image.new('1', (w, h), 0)

    def _restore_previous_image(self):
        # Use whatever InkyPi saves as the "last shown" image
        if os.path.isfile(self.current_image_path):
            try:
                img = Image.open(self.current_image_path).convert("RGB")
                self.display_manager.display_image(img,
                                                   image_settings=self.device_config.get_config("image_settings", []))
                return True
            except Exception as e:
                logger.exception(
                    "Failed to load/restore previous image: %s", e)
        # Fallback to white if nothing to restore
        w, h = self._panel_size()
        img = Image.new("RGB", (w, h), "white")
        self.display_manager.display_image(img,
                                           image_settings=self.device_config.get_config("image_settings", []))
        return False

    # --- Events ---
    def _on_button_pressed(self):
        self.logger.info("GPIO23 pressed: turning display OFF (black + sleep)")
        try:
            self.display_manager.display_image(self._black_image())
            # Optional: sleep panel to save power (wrapped to not crash if missing)
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
            # Optional wake
            try:
                self.display_manager.wake()
            except Exception:
                pass

            if os.path.isfile(self.current_image_path):
                from PIL import Image
                img = Image.open(self.current_image_path)
                self.display_manager.display_image(img)
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
                if os.path.isfile(self.current_image_path):
                    img = Image.open(self.current_image_path)
                    self.display_manager.display_image(img)
                self._is_asleep = False
            except Exception as e:
                self.logger.exception("Error handling PIR wake: %s", e)

    def run(self):
        logger.info(
            "GPIO input manager thread started (Button=GPIO23, PIR=GPIO16)")
        # Just keep the thread alive
        while True:
            time.sleep(1)
