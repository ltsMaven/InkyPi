import os
import json
import logging
from dotenv import load_dotenv
from model import PlaylistManager, RefreshInfo

logger = logging.getLogger(__name__)


class Config:
    # Base path for the project directory
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    # File paths relative to the script's directory
    config_file = os.path.join(BASE_DIR, "config", "device.json")

    # File path for storing the current image being displayed
    current_image_file = os.path.join(
        BASE_DIR, "static", "images", "current_image.png")

    # Directory path for storing plugin instance images
    plugin_image_dir = os.path.join(BASE_DIR, "static", "images", "plugins")

    def __init__(self):
        self.config = self.read_config()

        # --- self-heal missing blocks (optional but recommended) -------------
        changed = False
        if not self.config.get("playlist_config"):
            self.config["playlist_config"] = {
                "playlists": [], "active_playlist": None}
            changed = True
        if not self.config.get("refresh_info"):
            self.config["refresh_info"] = {
                "refresh_time": None,
                "image_hash": "",
                "plugin_id": None,
                "plugin_instance": None,
            }
            changed = True
        if changed:
            # persist the fixed structure so future boots are safe
            self.write_config()

        # ---------------------------------------------------------------------
        self.plugins_list = self.read_plugins_list()
        self.playlist_manager = self.load_playlist_manager()
        self.refresh_info = self.load_refresh_info()

    # --------------------------- basic I/O ----------------------------------

    def read_config(self):
        """Reads the device config JSON file and returns it as a dictionary."""
        logger.debug(f"Reading device config from {self.config_file}")
        with open(self.config_file) as f:
            config = json.load(f)
        logger.debug("Loaded config:\n%s", json.dumps(config, indent=3))
        return config

    def write_config(self):
        """Updates the cached config from the model objects and writes to the config file."""
        logger.debug(f"Writing device config to {self.config_file}")
        # reflect current in-memory model objects
        if hasattr(self, "playlist_manager") and self.playlist_manager:
            self.update_value("playlist_config",
                              self.playlist_manager.to_dict())
        if hasattr(self, "refresh_info") and self.refresh_info:
            self.update_value("refresh_info", self.refresh_info.to_dict())
        with open(self.config_file, 'w') as outfile:
            json.dump(self.config, outfile, indent=4)

    # -------------------------- getters / setters ---------------------------

    def get_config(self, key=None, default=None):
        if key is not None:
            return self.config.get(key, default)
        return self.config

    def update_config(self, config):
        """Bulk update values and persist."""
        self.config.update(config)
        self.write_config()

    def update_value(self, key, value, write=False):
        """Update a single key; optionally persist immediately."""
        self.config[key] = value
        if write:
            self.write_config()

    # ---------------------------- models ------------------------------------

    def load_playlist_manager(self):
        """Resilient load: tolerate missing/null structure."""
        data = self.get_config("playlist_config", {}) or {}
        pm = PlaylistManager.from_dict(data)
        if not pm.playlists:
            pm.add_default_playlist()
        return pm

    def load_refresh_info(self):
        """Resilient load: tolerate missing/null structure."""
        data = self.get_config("refresh_info", {}) or {}
        return RefreshInfo.from_dict(data)

    def get_playlist_manager(self):
        return self.playlist_manager

    def get_refresh_info(self):
        return self.refresh_info

    # ---------------------------- plugins -----------------------------------

    def read_plugins_list(self):
        """Reads the plugin-info.json from each plugin folder. Excludes __pycache__."""
        plugins_list = []
        plugins_dir = os.path.join(self.BASE_DIR, "plugins")
        for plugin in sorted(os.listdir(plugins_dir)):
            plugin_path = os.path.join(plugins_dir, plugin)
            if os.path.isdir(plugin_path) and plugin != "__pycache__":
                info_path = os.path.join(plugin_path, "plugin-info.json")
                if os.path.isfile(info_path):
                    logger.debug(f"Reading plugin info from {info_path}")
                    with open(info_path) as f:
                        plugins_list.append(json.load(f))
        return plugins_list

    def get_plugins(self):
        return self.plugins_list

    def get_plugin(self, plugin_id):
        return next((p for p in self.plugins_list if p.get('id') == plugin_id), None)

    # ----------------------------- misc -------------------------------------

    def get_resolution(self):
        """Returns (width, height) from config with a safe fallback."""
        res = self.get_config("resolution", (800, 480))
        try:
            w, h = res
        except Exception:
            w, h = (800, 480)
        return int(w), int(h)

    # alias for legacy callers
    get_display_dimensions = get_resolution

    def load_env_key(self, key):
        """Loads an environment variable using dotenv and returns its value."""
        load_dotenv(override=True)
        return os.getenv(key)
