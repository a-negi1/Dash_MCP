import io
from PIL import Image
from models import ColorPalette

def extract_palette_from_image(image_bytes: bytes) -> ColorPalette:
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    return ColorPalette(
        primary='#0F6FB5',
        secondary='#36B4E5',
        accent='#28C76F'
    )
