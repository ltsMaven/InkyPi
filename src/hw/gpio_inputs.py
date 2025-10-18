# src/hw/gpio_inputs.py
import os
import threading
import time
import logging
from PIL import Image
from gpiozero import Button, MotionSensor
from refresh_task import ManualRefresh  # PIR removed to avoid unintended wakes

logger = logging.getLogger(__name__)


class GpioInputManager(threading.Thread):
    """
    Button on GPIO23:
      - On every press: draw a BLACK frame (do NOT save to cache) and sleep the panel.
    """

    def __init__(self, display_manager, device_config, current_image_path, refresh_task):
        super().__init__(daemon=True)
        self.display_manager = display_manager
        self.device_config = device_config
        self.current_image_path = current_image_path
        self.refresh_task = refresh_task

        self.logger = logger
        self._lock = threading.RLock()
        self._is_asleep = False

        self.ai_motion_enabled = bool(
            self.device_config.get_config("ai_quote_on_motion", False))
        self.motion_cooldown = int(self.device_config.get_config(
            "pir_quote_cooldown_seconds", 20))
        self._last_motion_ts = 0

        # Inputs (BCM numbering)
        self.button = Button(23, pull_up=True, bounce_time=0.10)
        self.button.when_pressed = self._press_black  # release ignored
        self.pir.when_motion = self._on_motion

        self.pir = None
        if self.ai_motion_enabled:
            try:
                self.pir = MotionSensor(16)
                self.pir.when_motion = self._on_motion
                self.logger.info(
                    "PIR enabled on GPIO16 with %ss cooldown", self.motion_cooldown)
            except Exception as e:
                self.ai_motion_enabled = False
                self.logger.exception(
                    "Failed to init PIR; disabling motion feature: %s", e)

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

    def _on_motion(self):
        # Quick outs
        if not self.ai_motion_enabled:
            return
        if self.display_manager.is_asleep() or self._is_asleep:
            return

        # Only when AI Text is currently displayed
        try:
            info = self.device_config.get_refresh_info()  # RefreshInfo object
            current_plugin_id = getattr(info, "plugin_id", None)
        except Exception:
            current_plugin_id = None

        if current_plugin_id != "ai_text":
            return

        # Cooldown
        now = time.time()
        if (now - self._last_motion_ts) < self.motion_cooldown:
            return

        with self._lock:
            now = time.time()
            if (now - self._last_motion_ts) < self.motion_cooldown:
                return
            self._last_motion_ts = now

        self.logger.info("PIR: AI Text on-screen → generating a new quote")
        try:
            action = ManualRefresh(plugin_id="ai_text", plugin_settings={})
            self.refresh_task.manual_update(action)
        except Exception as e:
            self.logger.exception("PIR-triggered quote refresh failed: %s", e)

    # --- thread loop ---------------------------------------------------------

    def run(self):
        self.logger.info("GPIO input manager thread started (Button=GPIO23)")
        while True:
            time.sleep(1)
