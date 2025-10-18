#!/usr/bin/env python3
import argparse
import inspect
import logging
import logging.config
import os
import random
import sys
import time
import warnings

from flask import Flask
from jinja2 import ChoiceLoader, FileSystemLoader
from waitress import serve

from blueprints.main import main_bp
from blueprints.plugin import plugin_bp
from blueprints.playlist import playlist_bp
from blueprints.settings import settings_bp
from config import Config
from display.display_manager import DisplayManager
import display.display_manager as dm
from hw.gpio_inputs import GpioInputManager
from plugins.plugin_registry import load_plugins
from refresh_task import RefreshTask
from utils.app_utils import generate_startup_image

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.config.fileConfig(os.path.join(
    os.path.dirname(__file__), 'config', 'logging.conf'))
warnings.filterwarnings("ignore", message=".*Busy Wait: Held high.*")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CLI args
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser(description='InkyPi Display Server')
parser.add_argument('--dev', action='store_true',
                    help='Run in development mode')
args = parser.parse_args()

if args.dev:
    Config.config_file = os.path.join(
        Config.BASE_DIR, "config", "device_dev.json")
    DEV_MODE = True
    PORT = 8080
    logger.info("Starting InkyPi in DEVELOPMENT mode on port 8080")
else:
    DEV_MODE = False
    PORT = 80
    logger.info("Starting InkyPi in PRODUCTION mode on port 80")

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
logging.getLogger('waitress.queue').setLevel(logging.ERROR)
app = Flask(__name__)
template_dirs = [
    os.path.join(os.path.dirname(__file__), "templates"),
    os.path.join(os.path.dirname(__file__), "plugins"),
]
app.jinja_loader = ChoiceLoader(
    [FileSystemLoader(directory) for directory in template_dirs])

# ---------------------------------------------------------------------------
# Core objects (order matters)
# ---------------------------------------------------------------------------
device_config = Config()
display_manager = DisplayManager(device_config)

logger.info("DisplayManager module file: %s", dm.__file__)
logger.info("DM.display_image sig: %s",
            inspect.signature(display_manager.display_image))
logger.info("Has display_image? %s", hasattr(display_manager, "display_image"))
logger.info("DisplayManager methods: %s", [
            m for m in dir(display_manager) if m.startswith("display")])

# FIX: create before using in GPIO manager
refresh_task = RefreshTask(device_config, display_manager)

# Paths used by GPIO manager (define BEFORE we try to create GPIO mgr)
CURRENT_IMAGE_PATH = os.path.join(os.path.dirname(
    __file__), "static", "images", "current_image.png")  # FIX: move up
BLACK_IMAGE_PATH = os.path.join(os.path.dirname(
    __file__), "static", "images", "black.png")             # FIX: move up


def ensure_black_image(path, size):
    from PIL import Image
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        if not os.path.isfile(path):
            Image.new("RGB", size, "black").save(path)
        else:
            with Image.open(path) as im:
                if im.size != size:
                    Image.new("RGB", size, "black").save(path)
    except Exception:
        Image.new("RGB", size, "black").save(path)


# Make sure the black image matches panel size
panel_wh = device_config.get_resolution()
if device_config.get_config("orientation") == "vertical":
    panel_wh = panel_wh[::-1]
ensure_black_image(BLACK_IMAGE_PATH, panel_wh)

# Expose to app
app.config['DEVICE_CONFIG'] = device_config
app.config['DISPLAY_MANAGER'] = display_manager
app.config['REFRESH_TASK'] = refresh_task
app.config['MAX_FORM_PARTS'] = 10_000

# Register blueprints
app.register_blueprint(main_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(plugin_bp)
app.register_blueprint(playlist_bp)

# Singleton handle for the GPIO thread
__GPIO_MGR__ = None  # FIX: explicit global handle

if __name__ == '__main__':
    # ---------- Start GPIO manager ONCE ----------
    try:
        if __GPIO_MGR__ is None or not __GPIO_MGR__.is_alive():               # FIX: single start
            __GPIO_MGR__ = GpioInputManager(
                display_manager,
                device_config,
                CURRENT_IMAGE_PATH,
                refresh_task,
                BLACK_IMAGE_PATH
            )
            __GPIO_MGR__.start()
            logger.info("GPIO input manager started")
        else:
            logger.info("GPIO input manager already running; skipping")
    except Exception as e:
        logger.exception("Failed to start GPIO input manager: %s", e)

    # ---------- Start background refresh ----------
    refresh_task.start()

    # ---------- Startup splash (once) ----------
    if device_config.get_config("startup") is True:
        logger.info("Startup flag is set, displaying startup image")
        img = generate_startup_image(device_config.get_resolution())
        display_manager.display_image(img)
        device_config.update_value("startup", False, write=True)

    # ---------- Serve ----------
    try:
        app.secret_key = str(random.randint(100000, 999999))

        if DEV_MODE:
            import socket
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                s.close()
                logger.info(f"Serving on http://{local_ip}:{PORT}")
            except Exception:
                pass

        serve(app, host="0.0.0.0", port=PORT, threads=1)
    finally:
        refresh_task.stop()
