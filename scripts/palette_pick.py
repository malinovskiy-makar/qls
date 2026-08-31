"""Подбор трёх недосчитанных значений палитры (31.08.2026) замером, не на глаз.

Считает контраст WCAG 2.1 (относительная яркость), композит полупрозрачной
заливки на подложке и ΔE(CIE76, Lab) между двумя цветами. Печатает JSON
со всеми найденными значениями и промежуточными замерами для отчёта.
"""
import json


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb)


def _linear(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb):
    r, g, b = rgb
    return 0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b)


def contrast_ratio(rgb1, rgb2):
    l1 = relative_luminance(rgb1)
    l2 = relative_luminance(rgb2)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def composite(fg_rgb, alpha, bg_rgb):
    return tuple(fg_rgb[i] * alpha + bg_rgb[i] * (1 - alpha) for i in range(3))


def rgb_to_xyz(rgb):
    r, g, b = (_linear(c) for c in rgb)
    x = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
    y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
    z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041
    return x, y, z


def xyz_to_lab(xyz):
    xn, yn, zn = 0.95047, 1.0, 1.08883
    x, y, z = xyz[0] / xn, xyz[1] / yn, xyz[2] / zn

    def f(t):
        return t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116

    fx, fy, fz = f(x), f(y), f(z)
    L = 116 * fy - 16
    a = 500 * (fx - fy)
    b = 200 * (fy - fz)
    return L, a, b


def delta_e(hex1, hex2):
    lab1 = xyz_to_lab(rgb_to_xyz(hex_to_rgb(hex1)))
    lab2 = xyz_to_lab(rgb_to_xyz(hex_to_rgb(hex2)))
    return sum((a - b) ** 2 for a, b in zip(lab1, lab2)) ** 0.5


def rgb_to_hsl(rgb):
    r, g, b = (c / 255.0 for c in rgb)
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2
    if mx == mn:
        return 0.0, 0.0, l
    d = mx - mn
    s = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
    if mx == r:
        h = ((g - b) / d) % 6
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    h *= 60
    return h, s, l


def hsl_to_rgb_fixed(h, s, l):
    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = l - c / 2
    h = h % 360
    if h < 60:
        r, g, b = c, x, 0
    elif h < 120:
        r, g, b = x, c, 0
    elif h < 180:
        r, g, b = 0, c, x
    elif h < 240:
        r, g, b = 0, x, c
    elif h < 300:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x
    return tuple(round((v + m) * 255) for v in (r, g, b))


def find_amber_ink_light():
    surface = hex_to_rgb("#fffce6")
    tint = composite(hex_to_rgb("#96500c"), 0.11, surface)
    border = composite(hex_to_rgb("#96500c"), 0.34, surface)
    h, s, l = rgb_to_hsl(hex_to_rgb("#96500c"))
    for step in range(0, 60):
        cand_l = max(0.0, l - step * 0.005)
        cand = hsl_to_rgb_fixed(h, s, cand_l)
        c_tint = contrast_ratio(cand, tint)
        c_border = contrast_ratio(cand, border)
        if c_tint >= 4.6 and c_border >= 4.6:
            return {
                "value": rgb_to_hex(cand),
                "contrast_on_tint": round(c_tint, 2),
                "contrast_on_border": round(c_border, 2),
                "steps": step,
            }
    return None


def find_amber_ink_dark():
    surface = hex_to_rgb("#242019")
    tint = composite(hex_to_rgb("#e8925f"), 0.15, surface)
    border = composite(hex_to_rgb("#e8925f"), 0.34, surface)
    h, s, l = rgb_to_hsl(hex_to_rgb("#e8925f"))
    for step in range(0, 60):
        cand_l = min(1.0, l + step * 0.005)
        cand = hsl_to_rgb_fixed(h, s, cand_l)
        c_tint = contrast_ratio(cand, tint)
        c_border = contrast_ratio(cand, border)
        if c_tint >= 4.6 and c_border >= 4.6:
            return {
                "value": rgb_to_hex(cand),
                "contrast_on_tint": round(c_tint, 2),
                "contrast_on_border": round(c_border, 2),
                "steps": step,
            }
    return None


def find_surface_tool_dark():
    surface = hex_to_rgb("#242019")
    text = hex_to_rgb("#f2ecd9")
    start = hex_to_rgb("#22302f")
    h0, s0, l0 = rgb_to_hsl(start)
    best = None
    for dh in range(-20, 21, 2):
        for dl in [x / 1000 for x in range(-60, 61, 5)]:
            for ds in [x / 100 for x in range(-20, 21, 5)]:
                h = h0 + dh
                l = max(0.0, min(1.0, l0 + dl))
                s = max(0.0, min(1.0, s0 + ds))
                cand = hsl_to_rgb_fixed(h, s, l)
                if cand[2] <= cand[0]:
                    continue
                c_surf = contrast_ratio(cand, surface)
                if not (1.08 <= c_surf <= 1.22):
                    continue
                c_text = contrast_ratio(text, cand)
                if c_text < 4.6:
                    continue
                dist = abs(dh) + abs(dl) * 100 + abs(ds) * 100
                if best is None or dist < best[0]:
                    best = (dist, cand, c_surf, c_text)
    if best is None:
        return None
    _, cand, c_surf, c_text = best
    return {
        "value": rgb_to_hex(cand),
        "contrast_to_surface": round(c_surf, 3),
        "contrast_text": round(c_text, 2),
        "b_gt_r": cand[2] > cand[0],
    }


def main():
    result = {}
    result["amber_ink_light"] = find_amber_ink_light()
    result["amber_ink_dark"] = find_amber_ink_dark()
    result["surface_tool_dark"] = find_surface_tool_dark()

    # map-node против нового фона карты (--bg)
    bg_light = hex_to_rgb("#f4eed2")
    bg_dark = hex_to_rgb("#191612")
    result["map_node_light_vs_bg"] = round(contrast_ratio(hex_to_rgb("#4A5260"), bg_light), 2)
    result["map_node_dark_vs_bg"] = round(contrast_ratio(hex_to_rgb("#C8CEDA"), bg_dark), 2)

    # ΔE между --brand-amber и --amber в обеих темах
    result["delta_e_light"] = round(delta_e("#d6a525", "#96500c"), 1)
    result["delta_e_dark"] = round(delta_e("#d6a525", "#e8925f"), 1)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
