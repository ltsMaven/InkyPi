# src/hw/gpio_inputs.py
import threading
import time
import logging
from PIL import Image
from gpiozero import Button, MotionSensor
from refresh_task import ManualRefresh

logger = logging.getLogger(__name__)


class GpioInputManager(threading.Thread):
    """
    GPIO:
      - Button (GPIO23): draw a BLACK frame (no cache write) and sleep the panel.
      - PIR (GPIO16, optional): when AI Text is on-screen, generate a new quote with cooldown.
    """

    def __init__(self, display_manager, device_config, current_image_path, refresh_task, black_image_path=None):
        super().__init__(daemon=True)
        self.display_manager = display_manager
        self.device_config = device_config
        self.current_image_path = current_image_path
        self.refresh_task = refresh_task
        self.black_image_path = black_image_path

        self.logger = logger
        self._lock = threading.RLock()
        self._is_asleep = False

        # Motion feature flags
        self.ai_motion_enabled = bool(
            self.device_config.get_config("ai_quote_on_motion", False))
        self.motion_cooldown = int(self.device_config.get_config(
            "pir_quote_cooldown_seconds", 20))
        self._last_motion_ts = 0

        # Button (BCM numbering)
        self.button = Button(23, pull_up=True, bounce_time=0.10)
        self.button.when_pressed = self._press_black  # release ignored

        self.pir = None
        if self.ai_motion_enabled:
            try:
                self.pir = MotionSensor(16)
                self.pir.when_motion = self._on_motion  # <-- bind AFTER creating self.pir
                self.logger.info(
                    "PIR enabled on GPIO16 with %ss cooldown", self.motion_cooldown)
            except Exception as e:
                self.ai_motion_enabled = False
                self.logger.exception(
                    "Failed to init PIR; disabling motion feature: %s", e)

    # --- helpers -------------------------------------------------------------

    def _panel_size(self):
        get_res = getattr(self.device_config, "get_resolution", None)
        if callable(get_res):
            w, h = get_res()
        else:
            get_dims = getattr(self.device_config,
                               "get_display_dimensions", None)
            if not callable(get_dims):
                raise AttributeError(
                    "device_config must implement get_resolution() or get_display_dimensions()")
            w, h = get_dims()
        return int(w), int(h)

    def _black_image(self):
        w, h = self._panel_size()
        return Image.new("RGB", (w, h), "black")

    def _display(self, pil_image, save_to_cache=True):
        self.display_manager.display_image(
            pil_image, save_to_cache=save_to_cache)

    # --- button handler ------------------------------------------------------

    def _press_black(self):
        """Always draw local black image (fallback to generated), then sleep (no cache write)."""
        with self._lock:
            try:
                self.logger.info("Button: draw LOCAL black (no cache write) + sleep")

                # Prefer the pre-made on-disk black image if provided
                img = None
                if getattr(self, "black_image_path", None):
                    try:
                        img = Image.open(self.black_image_path).convert("RGB")
                    except Exception:
                        img = None

                # Fallback: generate a solid black at panel size
                if img is None:
                    w, h = self._panel_size()
                    img = Image.new("RGB", (w, h), "black")

                # Do not overwrite current_image.png when blanking
                self._display(img, save_to_cache=False)

                # Ensure hardware draw finishes, then sleep the panel
                try:
                    self.display_manager.wait_until_idle()
                except Exception:
                    pass

                try:
                    self.display_manager.sleep()
                except Exception:
                    pass
                self._is_asleep = True
            except Exception as e:
                self.logger.exception("Error handling button press: %s", e)

    # --- PIR motion -> new AI quote -----------------------------------------

    def _on_motion(self):
        if not self.ai_motion_enabled:
            return
        if self.display_manager.is_asleep() or self._is_asleep:
            return

        try:
            info = self.device_config.get_refresh_info()
            current_plugin_id = getattr(info, "plugin_id", None)
        except Exception:
            current_plugin_id = None

        if current_plugin_id != "ai_text":
            return

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
        self.logger.info(
            "GPIO input manager thread started (Button=GPIO23%s)",
            ", PIR=GPIO16" if self.pir else ""
        )
        while True:
            time.sleep(1)
