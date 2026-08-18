"""Generate 易知 app icon (icon.ico / icon.png). Run: python electron/scripts/generate_icon.py"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(__file__).resolve().parent.parent / "assets"
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\msyhl.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\msyh.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
]


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for fp in FONT_CANDIDATES:
        if Path(fp).is_file():
            try:
                return ImageFont.truetype(fp, size)
            except OSError:
                continue
    return ImageFont.load_default()


def create_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = max(1, int(size * 0.06))
    radius = max(2, int(size * 0.22))

    base = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bdraw = ImageDraw.Draw(base)
    bdraw.rounded_rectangle(
        (pad, pad, size - pad, size - pad),
        radius=radius,
        fill=(37, 99, 235, 255),
    )
    hi = max(1, int(size * 0.04))
    bdraw.rounded_rectangle(
        (pad + hi, pad + hi, size - pad - hi, int(size * 0.58)),
        radius=max(1, radius - hi),
        fill=(59, 130, 246, 90),
    )
    img = Image.alpha_composite(img, base)
    draw = ImageDraw.Draw(img)

    dot_r = max(1, int(size * 0.045))
    cx = size - pad - dot_r * 3
    cy = size - pad - dot_r * 3
    draw.ellipse(
        (cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r),
        fill=(219, 234, 254, 230),
    )

    font = load_font(int(size * 0.56))
    char = "易"
    bbox = draw.textbbox((0, 0), char, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = (size - tw) // 2 - bbox[0]
    ty = (size - th) // 2 - bbox[1] - int(size * 0.02)
    draw.text((tx, ty), char, font=font, fill=(255, 255, 255, 255))
    return img


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    icons = [create_icon(s) for s in sizes]
    icons[-1].save(ASSETS / "icon.png")
    icons[-1].save(ASSETS / "icon-256.png")
    create_icon(512).save(ASSETS / "icon-512.png")
    icons[0].save(
        ASSETS / "icon.ico",
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=icons[1:],
    )
    print(f"Wrote icons to {ASSETS}")


if __name__ == "__main__":
    main()
