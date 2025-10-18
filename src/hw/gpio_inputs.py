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
      - Button on GPIO23: press to toggle OFF/ON.
      - PIR on GPIO16: if display is OFF (asleep), wake and restore last image.
    """

    def __init__(self, display_manager, device_config, current_image_path):
        super().__init__(daemon=True)
        self.display_manager = display_manager
        self.device_config = device_config
        self.current_image_path = current_image_path

        # Logging + concurrency
        self.logger = logger
        self._lock = threading.RLock()
        self._is_asleep = False  # start awake by default

        # Inputs (BCM numbering)
        self.button = Button(23, pull_up=True, bounce_time=0.10)
        self.pir = MotionSensor(16)  # tune thresholds if needed

        # Bind events (press toggles; release ignored)
        self.button.when_pressed = self._toggle_power
        # If you don't want PIR wake, comment out the next line:
        self.pir.when_motion = self._on_motion

    # --- Helpers -------------------------------------------------------------

    def _panel_size(self):
        """Query panel resolution from config (supports legacy method name)."""
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
        # Use RGB to avoid 1-bit mode pitfalls in some pipelines
        return Image.new("RGB", (w, h), "black")

    def _display(self, pil_image, save_to_cache=True):
        """Centralized draw; lets DisplayManager handle transforms & caching."""
        self.display_manager.display_image(
            pil_image, save_to_cache=save_to_cache)

    def _restore_previous_image(self):
        """Load last cached image (written by DisplayManager) and display it."""
        path = self.current_image_path
        exists = os.path.isfile(path)
        size = os.path.getsize(path) if exists else 0
        self.logger.info(
            "Restoring from %s (exists=%s, size=%s bytes)", path, exists, size)

        if exists and size > 0:
            try:
                # Open+copy so the file handle is released before we draw/save again
                with Image.open(path) as im:
                    img = im.convert("RGB").copy()
                # save_to_cache=True by default (fine while awake)
                self._display(img)
                return True
            except Exception as e:
                self.logger.exception(
                    "Failed to load/restore previous image: %s", e)

        # Fallback: white frame if nothing cached
        w, h = self._panel_size()
        self._display(Image.new("RGB", (w, h), "white"))
        return False

    # --- Button / PIR handlers ----------------------------------------------

    def _toggle_power(self):
        """Single-press toggle: if asleep -> wake+restore, else -> black+sleep."""
        with self._lock:
            if self._is_asleep:
                # ---- WAKE PATH ----
                self.logger.info("Button: WAKE + clear + restore")
                try:
                    self.display_manager.wake()
                except Exception:
                    pass

                # Optional but recommended: clean the panel to avoid ghosting
                try:
                    self.display_manager.clear_panel(to_white=True)
                except Exception:
                    pass

                self._restore_previous_image()
                self._is_asleep = False
            else:
                # ---- SLEEP PATH ----
                self.logger.info("Button: SLEEP (black, no cache write)")
                # Draw black but DO NOT overwrite current_image.png
                self._display(self._black_image(), save_to_cache=False)

                # Ensure the black refresh completed before sleeping
                try:
                    self.display_manager.wait_until_idle()
                except Exception:
                    pass

                try:
                    self.display_manager.sleep()
                except Exception:
                    pass

                self._is_asleep = True

    def _on_motion(self):
        """If asleep, wake on motion and restore last image."""
        with self._lock:
            if not self._is_asleep:
                return
            self.logger.info("PIR motion: wake + restore last image")
            try:
                self.display_manager.wake()
            except Exception:
                pass
            # Optional: clear first to reduce banding/ghosting
            try:
                self.display_manager.clear_panel(to_white=True)
            except Exception:
                pass
            self._restore_previous_image()
            self._is_asleep = False

    # --- Thread loop ---------------------------------------------------------

    def run(self):
        self.logger.info(
            "GPIO input manager thread started (Button=GPIO23, PIR=GPIO16)")
        while True:
            time.sleep(1)
