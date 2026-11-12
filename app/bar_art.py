from functools import lru_cache
from math import pi, sin, tau

import numpy as np
from PIL import Image, ImageDraw


BACKGROUND = "#080f1c"
WAVE_HEIGHT = 53


def save_tray_icon(path):
    image = Image.new("RGBA", (96, 96))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((3, 3, 92, 92), radius=25, fill="#111a30", outline="#314466", width=5)
    x = np.arange(14, 83)
    phase = (x - x[0]) / (x[-1] - x[0])
    taper = np.sin(pi * phase)
    wave = -22 * np.sin(tau * phase) * taper
    for offset, color, width in ((7, "#8c78f5", 7), (-4, "#9cecff", 8)):
        points = list(zip(x.tolist(), (48 + wave + offset * taper).tolist()))
        draw.line(points, fill=color, width=width, joint="curve")
    path.parent.mkdir(exist_ok=True)
    image.save(path, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48)])


@lru_cache(maxsize=4)
def bar_shadow(width):
    shade = Image.new("RGBA", (width, WAVE_HEIGHT), (4, 6, 12))
    y = np.linspace(0, 1, WAVE_HEIGHT)
    alpha = np.rint(86 * (1 - y) ** 1.35).astype(np.uint8)
    shade.putalpha(Image.fromarray(np.broadcast_to(alpha[:, None], (WAVE_HEIGHT, width))))
    return shade


WAVE_PALETTES = {
    "closed": ((138, 34, 64), (208, 43, 71), (249, 88, 106), (255, 159, 153)),
    "ready": ((95, 76, 184), (104, 114, 218), (140, 164, 241), (179, 193, 249)),
    "listening": ((43, 133, 106), (45, 195, 135), (96, 243, 166), (174, 255, 203)),
    "speaking": ((115, 103, 251), (78, 158, 255), (110, 230, 255), (183, 248, 255)),
}
WAVE_LAYERS = ((1.0, 1.45, 1.1), (1.25, 1.75, 0.85), (1.55, 2.03, 1.0), (1.1, 2.25, 0.7))
WAVE_ROWS = np.arange(WAVE_HEIGHT, dtype=np.float32)[:, None] + 0.5


@lru_cache(maxsize=4)
def wave_geometry(width):
    sample_count = max(1, min(3, 1200 // width))
    samples = (np.arange(width * sample_count, dtype=np.float32) + 0.5) / sample_count
    inset = min(16, width * 0.06)
    position = np.clip((samples - inset) / (width - 2 * inset), 0, 1)
    taper = np.maximum(0, np.sin(pi * position)) ** 0.86
    edge = np.clip(np.minimum(position, 1 - position) / 0.11, 0, 1)
    fade = edge * edge * (3 - 2 * edge)
    return position, taper, fade, sample_count


def wave_frame(level, phase, width, palette, opacity=1.0):
    position, taper, fade, sample_count = wave_geometry(width)
    center = WAVE_HEIGHT / 2
    extent = 14 + 15 * level
    top = max(0, int(center - extent))
    bottom = min(WAVE_HEIGHT, int(center + extent) + 1)
    image = np.zeros((bottom - top, len(position), 4), dtype=np.float32)
    strokes = []
    glow_radius = 1.9 + 0.8 * level
    for index, (color, (line_width, frequency, gain)) in enumerate(zip(palette, WAVE_LAYERS)):
        drift = phase + index * 1.16
        breath = 0.79 + 0.21 * sin(drift)
        amplitude = (3.8 + level * 10.6) * gain
        shape = breath * np.sin(tau * frequency * position + index * 1.51)
        shape += 0.27 * np.sin(tau * 3.1 * position - index * 0.7)
        shape += 0.36 * np.sin(tau * 1.15 * position + drift)
        curve = center + amplitude * taper * shape
        slope_scale = np.hypot(1, np.gradient(curve) * sample_count)
        distance = WAVE_ROWS[top:bottom] - curve
        glow = np.exp(-0.5 * (distance / (glow_radius * slope_scale)) ** 2)
        glow *= fade * (0.085 + 0.25 * level)
        rgb = np.array((*color, 255), dtype=np.float32)
        image += (rgb - image) * glow[:, :, None]

        # Measure how much of each pixel the stroke covers, including fractions.
        half_width = line_width / 2 * slope_scale
        coverage = np.maximum(0, np.minimum(distance + 0.5, half_width)
                              - np.maximum(distance - 0.5, -half_width))
        strokes.append((rgb, coverage * fade * (0.35 + 0.65 * level)))

    for rgb, coverage in strokes:
        image += (rgb - image) * coverage[:, :, None]

    if sample_count > 1:
        image = image.reshape(bottom - top, width, sample_count, 4).mean(axis=2)
    image *= opacity
    band = Image.frombytes("RGBa", (width, bottom - top), np.rint(image).astype(np.uint8).tobytes()).convert("RGBA")
    frame = Image.new("RGBA", (width, WAVE_HEIGHT))
    frame.paste(band, (0, top))
    return frame
