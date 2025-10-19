from plugins.base_plugin.base_plugin import BasePlugin
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ToDoList(BasePlugin):
    def generate_settings_template(self):
        # keeps default style controls etc. like other plugins
        tpl = super().generate_settings_template()
        tpl['style_settings'] = True
        return tpl

    def generate_image(self, settings, device_config):
        title = (settings.get("title") or "To-Do").strip()

        # Collect up to 5 non-empty items from the saved settings
        items = []
        for i in range(1, 6):
            v = (settings.get(f"item{i}") or "").strip()
            if v:
                items.append(v)

        # Date label (adjust to your taste)
        date_str = datetime.now().strftime("%a, %d %b %Y")

        # Respect orientation
        w, h = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            w, h = h, w

        params = {
            "title": title,
            "date": date_str,
            "items": items,
            "plugin_settings": settings,
        }
        return self.render_image((w, h), "todo_list.html", "todo_list.css", params)
