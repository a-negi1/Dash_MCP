import json
import os
import base64
from io import BytesIO
from openai import OpenAI
from PIL import Image

MODEL = "llama-3.2-90b-vision-preview"

def _get_client() -> OpenAI:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY environment variable not set")
    return OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1"
    )

IMAGE_PALETTE_SYSTEM = """
Analyze this dashboard image and extract its visual design system.
Return ONLY valid JSON with this exact shape:

{
  "primary": "#2D5BFF",
  "secondary": "#1A3A8F",
  "accent": "#FF6B35",
  "background": "#FFFFFF",
  "text": "#252423",
  "data_colors": ["#2D5BFF", "#FF6B35", "#28C76F", "#EA5455", "#FF9F43", "#1E9AF5", "#9B59B6", "#2ECC71"],
  "style_notes": "dark navy header, minimal gridlines, rounded cards, sans-serif font",
  "chart_style": "flat",
  "border_radius": "soft"
}

data_colors: 8 hex values representing the chart series palette visible in the image.
Extract the ACTUAL colors from the image — do not invent colors not present.
style_notes: brief description of the overall aesthetic.
chart_style: flat | gradient | outlined | shadowed
border_radius: none | soft | rounded
"""

def _extract_palette_local(image_base64: str) -> dict:
    img_data = base64.b64decode(image_base64)
    img = Image.open(BytesIO(img_data)).convert("RGB")
    img.thumbnail((200, 200))
    pixels = list(img.getdata())
    from collections import Counter
    color_counts = Counter(pixels)
    top_colors = [c for c, _ in color_counts.most_common(8)]
    hex_colors = [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in top_colors]
    while len(hex_colors) < 8:
        hex_colors.append("#CCCCCC")
    return {
        "primary": hex_colors[0],
        "secondary": hex_colors[1] if len(hex_colors) > 1 else hex_colors[0],
        "accent": hex_colors[2] if len(hex_colors) > 2 else hex_colors[0],
        "background": "#FFFFFF",
        "text": "#252423",
        "data_colors": hex_colors[:8],
        "style_notes": "auto-extracted via local Pillow fallback",
        "chart_style": "flat",
        "border_radius": "soft"
    }

def extract_palette_from_image(image_base64: str, media_type: str = "image/png") -> dict:
    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=800,
            messages=[{
                "role": "system",
                "content": IMAGE_PALETTE_SYSTEM
            }, {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{image_base64}"
                        }
                    },
                    {
                        "type": "text",
                        "text": "Extract the color palette and style from this dashboard."
                    }
                ]
            }],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(raw)
    except Exception:
        return _extract_palette_local(image_base64)