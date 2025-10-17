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
        w, h = self.device_config.get_display_dimensions()  # usually (800, 480)
        return int(w), int(h)

    def _black_image(self):
        w, h = self._panel_size()
        return Image.new("RGB", (w, h), "black")

    def _restore_previous_image(self):
        # Use whatever InkyPi saves as the "last shown" image
        if os.path.isfile(self.current_image_path):
            try:
                img = Image.open(self.current_image_path).convert("RGB")
                self.display_manager.display_image(img,
                    image_settings=self.device_config.get_config("image_settings", []))
                return True
            except Exception as e:
                logger.exception("Failed to load/restore previous image: %s", e)
        # Fallback to white if nothing to restore
        w, h = self._panel_size()
        img = Image.new("RGB", (w, h), "white")
        self.display_manager.display_image(img,
            image_settings=self.device_config.get_config("image_settings", []))
        return False

    # --- Events ---
    def _on_button_pressed(self):
        with self._lock:
            if not self.display_off:
                # TURN OFF: draw black and sleep
                logger.info("GPIO23 pressed: turning display OFF (black + sleep)")
                try:
                    self.display_manager.display_image(self._black_image(),
                        image_settings=self.device_config.get_config("image_settings", []))
                    # put display into sleep to save power
                    self.display_manager.display.sleep()
                    self.display_off = True
                except Exception as e:
                    logger.exception("Error turning display off: %s", e)
            else:
                # TURN ON: wake and restore last image
                logger.info("GPIO23 pressed: waking display and restoring last image")
                try:
                    self.display_manager.display.wake()
                except Exception:
                    # Some drivers re-init instead of wake:
                    try:
                        self.display_manager.display.initialize_display()
                    except Exception:
                        logger.exception("Wake/init failed; continuing to restore image anyway")
                self._restore_previous_image()
                self.display_off = False

    def _on_motion(self):
        # If PIR fires while off, wake and restore
        with self._lock:
            if self.display_off:
                logger.info("Motion on GPIO16: waking display due to motion")
                try:
                    self.display_manager.display.wake()
                except Exception:
                    try:
                        self.display_manager.display.initialize_display()
                    except Exception:
                        logger.exception("Wake/init failed on motion")
                self._restore_previous_image()
                self.display_off = False

    def run(self):
        logger.info("GPIO input manager thread started (Button=GPIO23, PIR=GPIO16)")
        # Just keep the thread alive
        while True:
            time.sleep(1)