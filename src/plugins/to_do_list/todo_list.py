from plugins.base_plugin.base_plugin import BasePlugin
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class TodoList(BasePlugin):
    """
    Simple To-Do list plugin (up to 5 items).
    Settings page provides Title + 5 text fields.
    """

    def generate_settings_template(self):
        # Keep style controls if your base page supports it
        template_params = super().generate_settings_template()
        template_params['style_settings'] = True
        return template_params

    def generate_image(self, settings, device_config):
        title = (settings.get("title") or "To-Do").strip()

        # Collect up to 5 non-empty items in order
        items = []
        for i in range(1, 6):
            val = (settings.get(f"item{i}") or "").strip()
            if val:
                items.append(val)

        # Dimensions (respect orientation)
        w, h = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            w, h = h, w

        params = {
            "title": title,
            "items": items,
            "date": datetime.now().strftime("%a, %d %b"),
            "plugin_settings": settings,
        }

        return self.render_image(
            (w, h),
            "todo_list.html",
            "todo_list.css",
            params
        )
