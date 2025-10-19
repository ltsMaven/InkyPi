from plugins.base_plugin.base_plugin import BasePlugin
import logging

logger = logging.getLogger(__name__)


class TodoList(BasePlugin):
    """
    Simple plugin: renders up to 5 items as a to-do list.
    Uses 'title' (str) and 'items' (list of up to 5 strings) from settings.
    """

    def generate_settings_template(self):
        # Keep default style controls; no special fields needed
        t = super().generate_settings_template()
        t['style_settings'] = True
        return t

    def generate_image(self, settings, device_config):
        title = (settings or {}).get("title") or "To-Do"
        items = (settings or {}).get("items") or ["", "", "", "", ""]
        # Ensure exactly 5 strings
        items = [str(x or "").strip() for x in items][:5]
        while len(items) < 5:
            items.append("")

        w, h = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            w, h = h, w

        params = {
            "title": title,
            "items": items,
            "plugin_settings": settings or {}
        }
        # Render via plugin template + css in this folder
        return self.render_image((w, h), "todo_list.html", "todo_list.css", params)
