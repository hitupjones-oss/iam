"""Render IAM typography / logo layers as full-frame 1920x1080 RGBA PNGs.

Each AE comp in the brief (AE_01 ... AE_09) is broken into layers. A layer is a
full-frame transparent PNG with the element already positioned, plus timing
metadata (relative to the comp start) used by the ffmpeg review render, the
Premiere XML (V2+ graphics tracks) and the After Effects build script.

Motion rules (IAM Brand OS): entrance = opacity 0->100 + Y +16px->0 over
400-700ms with ease-out; exits are opacity only; no scale/bounce/rotation.
Gold (#B8A882) is never used here: ownership/equity/legal copy stays
black/white/platinum.
"""
import json
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, "assets", "fonts")
OUT = os.path.join(ROOT, "media", "03_GFX")
W, H = 1920, 1080

BLACK = (10, 10, 10)          # #0A0A0A Primary Black
WHITE = (245, 245, 240)       # #F5F5F0 Primary White
PLATINUM = (200, 200, 192)    # #C8C8C0 Platinum

LEGAL = "Nothing on this material is an offer of securities or investment advice."


def font(name, size, weight=None):
    path = {
        "montserrat": "Montserrat-VF.ttf",
        "playfair_italic": "PlayfairDisplay-Italic-VF.ttf",
        "dmmono": "DMMono-Regular.ttf",
        "dmmono_medium": "DMMono-Medium.ttf",
    }[name]
    f = ImageFont.truetype(os.path.join(FONTS, path), size)
    if weight is not None:
        f.set_variation_by_axes([weight])
    return f


def tracked_size(text, f, tracking):
    """Width/height of text drawn with extra letter spacing (tracking in em)."""
    extra = tracking * f.size
    w = 0
    for i, ch in enumerate(text):
        w += f.getlength(ch) + (extra if i < len(text) - 1 else 0)
    asc, desc = f.getmetrics()
    return w, asc + desc


def draw_tracked(img, text, f, tracking, color, cx, cy, align="center"):
    d = ImageDraw.Draw(img)
    w, h = tracked_size(text, f, tracking)
    x = cx - w / 2 if align == "center" else cx
    asc, desc = f.getmetrics()
    y = cy - (asc + desc) / 2
    extra = tracking * f.size
    for ch in text:
        d.text((x, y), ch, font=f, fill=color + (255,))
        x += f.getlength(ch) + extra
    return w, h


def blank():
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def logo(color=WHITE, height=120):
    """IAM mark from the client-supplied artwork (black glyphs on alpha) recoloured."""
    src = Image.open(os.path.join(ROOT, "assets", "logo", "IAM_logo_source.webp")).convert("RGBA")
    alpha = src.getchannel("A")
    bbox = alpha.getbbox()
    alpha = alpha.crop(bbox)
    mark = Image.new("RGBA", alpha.size, color + (255,))
    mark.putalpha(alpha)
    if height:
        w = round(mark.width * height / mark.height)
        mark = mark.resize((w, height), Image.LANCZOS)
    return mark


def scrim(cx, cy, rx, ry, strength=0.42):
    """Soft dark ellipse behind type so it reads over live action without a box."""
    m = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(m)
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=int(255 * strength))
    m = m.filter(ImageFilter.GaussianBlur(ry * 0.55))
    img = Image.new("RGBA", (W, H), BLACK + (0,))
    img.putalpha(m)
    return img


def save(img, comp, layer):
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, f"{comp}__{layer}.png")
    img.save(p)
    return os.path.relpath(p, ROOT)


def L(comp, layer, img, t_in=0.0, d_in=0.6, d_out=0.3, dy=16, hold_to_end=False):
    return dict(comp=comp, layer=layer, file=save(img, comp, layer), t_in=t_in,
                d_in=d_in, d_out=d_out, dy=dy, hold_to_end=hold_to_end)


def build():
    layers = []

    # AE_01 — over black, white on black, no gold
    c = "AE_01_DEMAND_CANNOT_BE_RENTED"
    img = blank()
    draw_tracked(img, "DEMAND CANNOT BE RENTED.", font("montserrat", 50, 600), 0.24, WHITE, W / 2, H / 2)
    layers.append(L(c, "text", img, d_in=0.65, d_out=0.35))

    # AE_02 — subtle IAM mark lower third over SHOT 13
    c = "AE_02_IAM_INTRO"
    img = blank()
    img.alpha_composite(scrim(W // 2, 905, 260, 70, 0.35))
    m = logo(WHITE, 46)
    img.alpha_composite(m, (W // 2 - m.width // 2, 905 - m.height // 2))
    layers.append(L(c, "mark", img, d_in=0.7, d_out=0.5))

    # AE_03..07 — operating model, one word at a time
    words = [("AE_03_UNDERWRITE", "UNDERWRITE", 1), ("AE_04_MATCH", "MATCH", 2),
             ("AE_05_FORM", "FORM", 3), ("AE_06_OPERATE", "OPERATE", 4),
             ("AE_07_COMPOUND", "COMPOUND", 5)]
    for comp, word, i in words:
        sc = scrim(W // 2, H // 2, 520, 120, 0.40)
        layers.append(L(comp, "scrim", sc, d_in=0.45, d_out=0.25, dy=0))
        img = blank()
        draw_tracked(img, f"{i:02d} / 05", font("dmmono", 20), 0.18, PLATINUM, W / 2, H / 2 - 62)
        layers.append(L(comp, "index", img, d_in=0.5, d_out=0.25))
        img = blank()
        draw_tracked(img, word, font("montserrat", 66, 600), 0.32, WHITE, W / 2, H / 2 + 6)
        layers.append(L(comp, "word", img, t_in=0.08, d_in=0.55, d_out=0.25))

    # AE_08 — end card lockup (nearly black frame, no extra animation: opacity only)
    c = "AE_08_FINAL_LOCKUP"
    img = blank()
    m = logo(WHITE, 112)
    img.alpha_composite(m, (W // 2 - m.width // 2, 430 - m.height // 2))
    layers.append(L(c, "mark", img, d_in=0.6, dy=0, hold_to_end=True))
    img = blank()
    draw_tracked(img, "INTELLECTUAL ASSET MANAGEMENT", font("montserrat", 24, 500), 0.42, PLATINUM, W / 2, 548)
    layers.append(L(c, "title", img, t_in=0.15, d_in=0.6, dy=0, hold_to_end=True))
    img = blank()
    draw_tracked(img, "A conversation between principals.", font("playfair_italic", 34, 400), 0.0, WHITE, W / 2, 628)
    layers.append(L(c, "tagline", img, t_in=0.7, d_in=0.6, dy=0, hold_to_end=True))

    # AE_09 — legal. Montserrat, platinum, upright, full opacity, readable size.
    c = "AE_09_LEGAL"
    img = blank()
    draw_tracked(img, LEGAL, font("montserrat", 23, 400), 0.02, PLATINUM, W / 2, 978)
    layers.append(L(c, "legal", img, t_in=0.15, d_in=0.4, dy=0, hold_to_end=True))

    # Standalone logo files for editorial / AE use
    logo(WHITE, None).save(os.path.join(ROOT, "assets", "logo", "IAM_logo_white.png"))
    logo((10, 10, 10), None).save(os.path.join(ROOT, "assets", "logo", "IAM_logo_black.png"))

    with open(os.path.join(OUT, "layers.json"), "w") as fh:
        json.dump(layers, fh, indent=1)
    return layers


if __name__ == "__main__":
    for l in build():
        print(l["comp"], l["layer"], l["file"])
