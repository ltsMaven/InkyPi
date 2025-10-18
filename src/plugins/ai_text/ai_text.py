from plugins.base_plugin.base_plugin import BasePlugin
from openai import OpenAI
from datetime import datetime
import logging
import re

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o-mini"  # fallback if none set in config


class AIText(BasePlugin):
    """
    Generates a short quote with a human author. The settings form has a single
    'Generate Quote' button that triggers a manual update for this plugin.
    """

    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['api_key'] = {
            "required": True,
            "service": "OpenAI",
            "expected_key": "OPEN_AI_SECRET"
        }
        template_params['style_settings'] = True
        return template_params

    def generate_image(self, settings, device_config):
        api_key = device_config.load_env_key("OPEN_AI_SECRET")
        if not api_key:
            raise RuntimeError("OPEN AI API Key not configured.")

        model = device_config.get_config("openai_model", DEFAULT_MODEL)
        title = settings.get("title") or "Quote"

        try:
            client = OpenAI(api_key=api_key)
            quote = AIText._fetch_random_quote(client, model)
        except Exception as e:
            logger.exception("Failed to fetch quote")
            raise RuntimeError(
                "OpenAI request failed; check logs and API key.") from e

        # Respect orientation
        w, h = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            w, h = h, w

        params = {
            "title": title,
            "content": quote,            # two lines: text then "— Author"
            "plugin_settings": settings,
        }
        return self.render_image((w, h), "ai_text.html", "ai_text.css", params)

    # ------------------ helpers ------------------

    @staticmethod
    def _fetch_random_quote(ai_client: OpenAI, model: str) -> str:
        """
        Return ONE real, verifiable quote by a human author, formatted as:

        <quote text>\n— <author name>

        The quote should be on themes like technology, learning, creativity, curiosity, or perseverance.
        No extra lines, no quotation marks.
        """
        system = (
            "You are a quotes generator. Produce ONE well-known, verifiable quote by a human author "
            "(not an AI). Topic should relate to technology, learning, creativity, curiosity, or perseverance. "
            "Constraints for the quote text (excluding author): 10–24 words. "
            "OUTPUT FORMAT EXACTLY:\n"
            "<quote text>\\n— <author full name>\n"
            "Do NOT add quotation marks, source links, years, or any extra text. "
            "Do NOT invent; if you are not certain of exact wording, respond with SKIP. "
            f"Today is {datetime.today().strftime('%Y-%m-%d')}."
        )
        user = "Return one quote now."

        # Up to 3 attempts in case the model replies SKIP or misformats
        for _ in range(3):
            resp = ai_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.7,
            )
            text = (resp.choices[0].message.content or "").strip()

            # Reject SKIP or empty
            if not text or text.upper().startswith("SKIP"):
                continue

            # Normalize smart quotes & trim
            text = text.replace("“", "").replace(
                "”", "").replace('"', "").strip()

            # Accept if it matches "<something>\n— <something>"
            if "\n— " in text:
                lines = text.splitlines()
                # squash any extra blank lines
                lines = [ln for ln in lines if ln.strip()]
                if len(lines) >= 2 and lines[1].lstrip().startswith("—"):
                    # Keep exactly two lines
                    quote_line = lines[0].strip()
                    author_line = lines[1].strip()
                    return f"{quote_line}\n{author_line}"

            # Try to coerce simple "<text> - Author" into desired form
            m = re.match(r"^(.*?)[\s\-–—]{1,2}\s*([A-Za-z][^,\n]+)$", text)
            if m:
                quote_line = m.group(1).strip()
                author = m.group(2).strip()
                if quote_line and author:
                    return f"{quote_line}\n— {author}"

        # Fallback: minimal safe message if all attempts fail
        return "Stay curious and keep learning.\n— Unknown"
