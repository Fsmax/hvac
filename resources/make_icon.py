# -*- coding: utf-8 -*-
"""Генератор иконки приложения.

Запуск:
    python resources/make_icon.py

Выходные файлы:
    resources/app.png    — 512x512 PNG (для README, web)
    resources/app.ico    — Windows multi-size ICO (16, 24, 32, 48, 64, 128, 256)
    resources/icon_*.png — отдельные размеры (для документации)

Дизайн: монограмма HC в фирменных цветах темы dark.qss
(bg #0F1419, accent #3B9EFF, белый текст). Соответствует UI приложения.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


# ----- Параметры дизайна -----
BG_TOP       = (28, 36, 47, 255)        # лёгкий вертикальный градиент
BG_BOTTOM    = (15, 20, 25, 255)        # #0F1419 (наш bg)
ACCENT       = (59, 158, 255, 255)      # #3B9EFF
WHITE        = (240, 244, 248, 255)
CORNER_PCT   = 0.22
BORDER_PCT   = 0.010
BORDER_COLOR = (60, 75, 95, 200)
MARGIN_PCT   = 0.18                     # внутренний отступ от краёв для текста

FONT_PATH = r"C:/Windows/Fonts/seguibl.ttf"   # Segoe UI Black


def _gradient_background(size: int) -> Image.Image:
    """Вертикальный градиент BG_TOP → BG_BOTTOM."""
    img = Image.new("RGB", (1, size))
    px = img.load()
    for y in range(size):
        t = y / max(1, size - 1)
        r = round(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t)
        g = round(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t)
        b = round(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t)
        px[0, y] = (r, g, b)
    return img.resize((size, size))


def _rounded_mask(size: int, radius: int) -> Image.Image:
    """Маска со скруглёнными углами."""
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [(0, 0), (size - 1, size - 1)], radius=radius, fill=255)
    return mask


def _fit_font_for_box(text: str, max_w: int, max_h: int) -> ImageFont.FreeTypeFont:
    """Подбирает размер так, чтобы текст влез И по ширине, И по высоте."""
    measure_canvas = ImageDraw.Draw(Image.new("L", (1, 1)))
    lo, hi = 10, max(max_w, max_h) * 2
    best = ImageFont.truetype(FONT_PATH, 10)
    while lo <= hi:
        mid = (lo + hi) // 2
        f = ImageFont.truetype(FONT_PATH, mid)
        bbox = measure_canvas.textbbox((0, 0), text, font=f, anchor="lt")
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if w <= max_w and h <= max_h:
            best = f
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def make_icon(size: int = 512) -> Image.Image:
    """Рисует иконку нужного размера и возвращает RGBA-Image."""
    # ---- Фон с градиентом и скруглением ----
    bg_rgb = _gradient_background(size)
    bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    radius = int(size * CORNER_PCT)
    mask = _rounded_mask(size, radius)
    bg.paste(bg_rgb, (0, 0), mask)

    # ---- Тонкая внутренняя обводка ----
    bw = max(1, int(size * BORDER_PCT))
    d = ImageDraw.Draw(bg)
    d.rounded_rectangle(
        [(bw // 2, bw // 2), (size - 1 - bw // 2, size - 1 - bw // 2)],
        radius=radius - bw // 2, outline=BORDER_COLOR, width=bw,
    )

    # ---- Лёгкий highlight в верхней половине (внутри маски) ----
    if size >= 64:
        hl = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        hd = ImageDraw.Draw(hl)
        hd.ellipse(
            [(-size * 0.3, -size * 0.7),
             (size * 1.3, size * 0.4)],
            fill=(255, 255, 255, 18),
        )
        hl.putalpha(Image.eval(hl.split()[3],
                                lambda a: a)) if False else None
        # Применяем маску скругления тоже
        masked_hl = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        masked_hl.paste(hl, (0, 0), mask)
        bg = Image.alpha_composite(bg, masked_hl)
        d = ImageDraw.Draw(bg)

    # ---- Монограмма HC ----
    text = "HC"
    margin = int(size * MARGIN_PCT)
    inner_w = size - 2 * margin
    inner_h = size - 2 * margin
    font = _fit_font_for_box(text, inner_w, inner_h)

    # Боксы для центрирования
    bbox_full = d.textbbox((0, 0), text, font=font, anchor="lt")
    bbox_h    = d.textbbox((0, 0), "H", font=font, anchor="lt")
    full_w = bbox_full[2] - bbox_full[0]
    full_h = bbox_full[3] - bbox_full[1]
    h_w    = bbox_h[2] - bbox_h[0]

    x0 = (size - full_w) // 2 - bbox_full[0]
    # Визуальный центр кириллицы/латиницы чуть выше геометрического
    y0 = (size - full_h) // 2 - bbox_full[1] - int(size * 0.015)

    # H — белая
    d.text((x0, y0), "H", fill=WHITE, font=font, anchor="lt")
    # C — акцентная, без жёсткого kerning
    d.text((x0 + h_w, y0), "C", fill=ACCENT, font=font, anchor="lt")

    # ---- Лёгкое свечение под акцентной буквой (только в крупных) ----
    if size >= 96:
        glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        glow_x = x0 + h_w + (bbox_full[2] - bbox_h[2]) // 2
        glow_y = y0 + full_h
        r = int(size * 0.22)
        gd.ellipse(
            [(glow_x - r, glow_y - r // 2),
             (glow_x + r, glow_y + r * 2)],
            fill=(*ACCENT[:3], 60),
        )
        glow = glow.filter(ImageFilter.GaussianBlur(radius=size * 0.04))
        # Только внутри маски
        masked_glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        masked_glow.paste(glow, (0, 0), mask)
        bg = Image.alpha_composite(bg, masked_glow)
        # Перерисуем текст ПОВЕРХ свечения, чтобы оно его не размывало
        d = ImageDraw.Draw(bg)
        d.text((x0, y0), "H", fill=WHITE, font=font, anchor="lt")
        d.text((x0 + h_w, y0), "C", fill=ACCENT, font=font, anchor="lt")

    return bg


def main() -> None:
    out_dir = Path(__file__).parent
    out_dir.mkdir(exist_ok=True)

    # Master 512x512 для README/web
    master = make_icon(512)
    master.save(out_dir / "app.png", "PNG")

    # Размеры для ICO + отдельные PNG
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = []
    for s in sizes:
        img = make_icon(s)
        img.save(out_dir / f"icon_{s}.png", "PNG")
        images.append(img)

    # Multi-size .ico для Windows
    images[-1].save(
        out_dir / "app.ico",
        format="ICO",
        sizes=[(im.width, im.height) for im in images],
        append_images=images[:-1],
    )

    print(f"OK -> {out_dir / 'app.ico'}")
    print(f"      {out_dir / 'app.png'} (512x512)")


if __name__ == "__main__":
    main()
