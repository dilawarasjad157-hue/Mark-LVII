"""Edit a photo with Pillow. The original is never overwritten."""
import os
from pathlib import Path

PLUGIN = {
    "name": "photo_editor",
    "description": (
        "Edit an image file: resize, crop, rotate, flip, grayscale, brightness, contrast, "
        "blur, sharpen, or convert format. Saves a NEW file next to the original. Use for "
        "'is photo ko edit karo', 'resize this picture', 'black and white banao'. "
        "Give a full path or just the file name."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file": {"type": "STRING", "description": "Image path or file name"},
            "operation": {"type": "STRING",
                          "description": "resize|crop|rotate|flip|grayscale|brightness|contrast|blur|sharpen|convert"},
            "width": {"type": "NUMBER", "description": "resize width in px"},
            "height": {"type": "NUMBER", "description": "resize height in px"},
            "degrees": {"type": "NUMBER", "description": "rotate angle"},
            "factor": {"type": "NUMBER", "description": "brightness/contrast factor, 1.0 = unchanged"},
            "box": {"type": "STRING", "description": "crop box as left,top,right,bottom in px"},
            "format": {"type": "STRING", "description": "convert target: png, jpg, webp"},
        },
        "required": ["file", "operation"],
    },
}


def _find(name: str) -> str | None:
    p = Path(name).expanduser()
    if p.exists():
        return str(p)
    home = Path.home()
    for d in ("Desktop", "Pictures", "Downloads", "Documents"):
        for root, _dirs, files in os.walk(home / d):
            for f in files:
                if f.lower() == p.name.lower():
                    return os.path.join(root, f)
    return None


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps
    except Exception:
        return "Pillow is not installed."
    try:
        src = _find(parameters.get("file", ""))
        if not src:
            return "I could not find that image."
        op = (parameters.get("operation") or "").lower()
        img = Image.open(src)
        img = ImageOps.exif_transpose(img)
        if op == "resize":
            w, h = parameters.get("width"), parameters.get("height")
            if not w and not h:
                return "Tell me the new width or height."
            if not w:
                w = int(img.width * (float(h) / img.height))
            if not h:
                h = int(img.height * (float(w) / img.width))
            img = img.resize((int(w), int(h)))
        elif op == "crop":
            box = [int(float(x)) for x in str(parameters.get("box", "")).split(",")]
            if len(box) != 4:
                return "Give the crop box as left,top,right,bottom."
            img = img.crop(box)
        elif op == "rotate":
            img = img.rotate(-float(parameters.get("degrees") or 90), expand=True)
        elif op == "flip":
            img = ImageOps.mirror(img)
        elif op == "grayscale":
            img = ImageOps.grayscale(img)
        elif op == "brightness":
            img = ImageEnhance.Brightness(img.convert("RGB")).enhance(float(parameters.get("factor") or 1.3))
        elif op == "contrast":
            img = ImageEnhance.Contrast(img.convert("RGB")).enhance(float(parameters.get("factor") or 1.3))
        elif op == "blur":
            img = img.filter(ImageFilter.GaussianBlur(3))
        elif op == "sharpen":
            img = img.filter(ImageFilter.SHARPEN)
        elif op != "convert":
            return "I do not know that edit."
        p = Path(src)
        ext = (parameters.get("format") or p.suffix.lstrip(".") or "png").lower().replace("jpeg", "jpg")
        out = p.with_name(f"{p.stem}_edited.{ext}")
        i = 2
        while out.exists():
            out = p.with_name(f"{p.stem}_edited{i}.{ext}")
            i += 1
        if ext == "jpg":
            img = img.convert("RGB")
        img.save(out, "JPEG" if ext == "jpg" else ext.upper())
        msg = f"Done. Saved as {out.name}; the original is untouched."
        if player:
            try:
                player.write_log(f"JARVIS: {msg} ({out})")
            except Exception:
                pass
        return msg
    except Exception as e:
        return f"Photo edit failed: {e}"
