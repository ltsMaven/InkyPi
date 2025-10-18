from plugins.base_plugin.base_plugin import BasePlugin
from openai import OpenAI
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o-mini"  # fallback if none set in config


class AIText(BasePlugin):
    """
    Generates a short, original AI-related quote. The settings form has a single
    'Generate Quote' button that triggers a manual update for this plugin.
    """

    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['api_key'] = {
            "required": True,
            "service": "OpenAI",
            "expected_key": "OPEN_AI_SECRET"
        }
        # Keep style controls if you want (font/size etc.)
        template_params['style_settings'] = True
        # (No textPrompt/textModel fields anymore)
        return template_params

    def generate_image(self, settings, device_config):
        # API key
        api_key = device_config.load_env_key("OPEN_AI_SECRET")
        if not api_key:
            raise RuntimeError("OPEN AI API Key not configured.")

        # Model (optional override from device config; otherwise default)
        model = device_config.get_config("openai_model", DEFAULT_MODEL)

        # Title (optional; can be themed in CSS/template)
        title = settings.get("title") or "AI Quote"

        # Call LLM to get a short, original quote about AI/tech/learning
        try:
            client = OpenAI(api_key=api_key)
            quote = AIText._fetch_random_quote(client, model)
        except Exception as e:
            logger.exception("Failed to fetch AI quote")
            raise RuntimeError(
                "OpenAI request failed; check logs and API key.") from e

        # Dimensions (respect orientation)
        width, height = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            width, height = height, width

        params = {
            "title": title,
            "content": quote,
            "plugin_settings": settings,
        }
        # Render using your existing HTML/CSS template
        return self.render_image((width, height), "ai_text.html", "ai_text.css", params)

    # ------------------ helpers ------------------

    @staticmethod
    def _fetch_random_quote(ai_client: OpenAI, model: str) -> str:
        """
        Ask the model for one short, original, attribution-free quote
        related to AI/technology/learning/curiosity. Keep it punchy.
        """
        system = (
            "You are a succinct quotes generator. Produce one original, "
            "inspirational quote related to AI/technology/learning/curiosity. "
            "Constraints: 10–22 words. Do NOT include an author name or quotes "
            "characters. Output only the quote text."
            f" Today is {datetime.today().strftime('%Y-%m-%d')}."
        )
        user = "Generate one original short quote now."

        resp = ai_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=1.0,
        )
        text = (resp.choices[0].message.content or "").strip()
        # Safety clamp: remove stray quotes/attributions if model slips
        text = text.replace("“", "").replace("”", "").replace('"', "")
        # Don’t allow multi-line blobs
        return text.splitlines()[0]
