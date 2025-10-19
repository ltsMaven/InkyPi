# plugins/todo_list/todo_list.py
from plugins.base_plugin.base_plugin import BasePlugin
from datetime import datetime


def _coerce_bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on", "checked")
    return False


class ToDoList(BasePlugin):
    def generate_settings_template(self):
        tpl = super().generate_settings_template()
        tpl['style_settings'] = True
        return tpl

    def generate_image(self, settings, device_config):
        title = (settings.get("title") or "To-Do").strip()
        items = []
        for i in range(1, 6):
            raw = (settings.get(f"item{i}") or "").strip()
            done = _coerce_bool(settings.get(f"done{i}", False))
            # Optional shorthand: "[x] " marks as done; "[ ] " marks not done
            if raw.startswith("[x] ") or raw.startswith("[X] "):
                done = True
                raw = raw[4:]
            elif raw.startswith("[ ] "):
                done = False
                raw = raw[4:]
            if raw:
                items.append({"text": raw, "done": done})

        date_str = datetime.now().strftime("%a, %d %b %Y")

        w, h = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            w, h = h, w

        params = {"title": title, "date": date_str,
                  "items": items, "plugin_settings": settings}
        return self.render_image((w, h), "todo_list.html", "todo_list.css", params)
