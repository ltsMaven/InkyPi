from plugins.base_plugin.base_plugin import BasePlugin
from datetime import datetime


class ToDoList(BasePlugin):
    def generate_settings_template(self):
        params = super().generate_settings_template()
        params['style_settings'] = True
        return params

    def generate_image(self, settings, device_config):
        title = (settings.get('title') or 'To-Do').strip()

        def truthy(v):
            if v is None:
                return False
            s = str(v).strip().lower()
            return s in ('1', 'true', 'on', 'yes', 'checked')

        items = []
        for i in range(1, 6):
            text = (settings.get(f'item{i}') or '').strip()
            if not text:
                continue
            done = truthy(settings.get(f'done{i}'))
            items.append({'text': text, 'done': done})

        w, h = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            w, h = h, w

        ctx = {
            "title": title,
            "date": datetime.now().strftime("%a, %d %b %Y"),
            "items": items,
            "plugin_settings": settings,
        }
        return self.render_image((w, h), "todo_list.html", "todo_list.css", ctx)
