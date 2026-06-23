from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

import ollama_tray.config as _cfg

_base: Image.Image | None = None
_icon_path: str | None = None


def set_icon_path(path: str | None) -> None:
    global _icon_path, _base
    _icon_path = path
    _base = None


def invalidate_cache() -> None:
    global _base
    _base = None


def _base_image() -> Image.Image:
    sz = _cfg.ICON_SIZE
    if _icon_path:
        try:
            img = Image.open(_icon_path).convert("RGBA")
            return img.resize((sz, sz), Image.LANCZOS)
        except (OSError, UnidentifiedImageError, ValueError):
            # Icon file corrupt or unreadable — fall through to generated icon
            pass

    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([2, 2, sz - 2, sz - 2], fill=(30, 30, 30, 230))
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont = ImageFont.load_default()
    for name in ("arial.ttf", "DejaVuSans-Bold.ttf"):
        try:
            font = ImageFont.truetype(name, 30)
            break
        except (OSError, IOError):
            continue
    draw.text((18, 14), "O", fill=(200, 200, 200), font=font)
    return img


def make_icon(status: str) -> Image.Image:
    global _base
    if _base is None:
        _base = _base_image()
    img = _base.copy()
    draw = ImageDraw.Draw(img)
    r = 10
    sz = _cfg.ICON_SIZE
    x0, y0 = sz - r * 2 - 2, sz - r * 2 - 2
    color = _cfg.STATUS_COLOR.get(status, _cfg.STATUS_COLOR["unknown"])
    draw.ellipse([x0 - 1, y0 - 1, x0 + r * 2 + 1, y0 + r * 2 + 1], fill=(0, 0, 0, 180))
    draw.ellipse([x0, y0, x0 + r * 2, y0 + r * 2], fill=color + (255,))
    return img
