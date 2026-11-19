"""WCAG 2.x contrast check for the frontend design tokens.

Reads `frontend/src/app/globals.css`, resolves the oklch tokens in `:root` (light) and `.dark`,
and checks the pairs below. Exit code 1 if any pair fails.

    python -I scripts/check_contrast.py
"""

import math
import re
import sys
from pathlib import Path

CSS = Path(__file__).resolve().parents[1] / "frontend" / "src" / "app" / "globals.css"

# (foreground, background, minimum). 4.5:1 = normal text (1.4.3); 3:1 = UI component boundaries
# and focus indicators (1.4.11).
CHECKS = [
    ("foreground", "background", 4.5),
    ("foreground", "card", 4.5),
    ("foreground", "muted", 4.5),
    ("muted-foreground", "background", 4.5),
    ("muted-foreground", "muted", 4.5),
    ("muted-foreground", "card", 4.5),
    ("primary-foreground", "primary", 4.5),
    ("primary", "background", 4.5),
    ("secondary-foreground", "secondary", 4.5),
    ("accent-foreground", "accent", 4.5),
    ("sidebar-accent-foreground", "sidebar-accent", 4.5),
    ("sidebar-foreground", "sidebar", 4.5),
    ("destructive", "background", 4.5),
    ("destructive", "card", 4.5),
    ("success", "background", 4.5),
    ("warning", "background", 4.5),
    ("info", "background", 4.5),
    ("foreground", "surface", 4.5),
    ("muted-foreground", "surface", 4.5),
    ("primary", "surface", 4.5),
    ("primary", "card", 4.5),
    ("primary", "accent", 4.5),
    ("success", "card", 4.5),
    ("success", "surface", 4.5),
    ("input", "background", 3.0),
    ("input", "card", 3.0),
    ("ring", "background", 3.0),
    ("ring", "sidebar", 3.0),
]

_OKLCH = re.compile(r"oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\w().-]+)\s*\)")


def _block(css: str, selector: str) -> dict[str, str]:
    match = re.search(re.escape(selector) + r"\s*\{(.*?)\}", css, re.S)
    if match is None:
        raise SystemExit(f"selector {selector!r} not found in {CSS}")
    return dict(re.findall(r"--([\w-]+)\s*:\s*([^;]+);", match.group(1)))


def _parse(value: str, hue_vars: dict[str, str]) -> tuple[float, float, float]:
    match = _OKLCH.search(value)
    if match is None:
        raise ValueError(f"not an opaque oklch() value: {value!r}")
    hue = match.group(3)
    var = re.fullmatch(r"var\(--([\w-]+)\)", hue)
    if var:
        hue = hue_vars[var.group(1)].split()[0]
    return float(match.group(1)), float(match.group(2)), float(hue)


def _linear_srgb(lightness: float, c: float, h: float) -> tuple[float, float, float]:
    a, b = c * math.cos(math.radians(h)), c * math.sin(math.radians(h))
    l_ = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    rgb = (
        4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
        -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
        -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_,
    )
    return tuple(min(1.0, max(0.0, v)) for v in rgb)  # type: ignore[return-value]


def _ratio(fg: tuple[float, float, float], bg: tuple[float, float, float]) -> float:
    def lum(color: tuple[float, float, float]) -> float:
        r, g, b = _linear_srgb(*color)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    hi, lo = sorted((lum(fg), lum(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def main() -> int:
    css = CSS.read_text(encoding="utf-8")
    light = _block(css, ":root")
    dark = {**light, **_block(css, ".dark")}
    failures = 0
    for theme_name, tokens in (("light", light), ("dark", dark)):
        for fg, bg, minimum in CHECKS:
            value = _ratio(_parse(tokens[fg], tokens), _parse(tokens[bg], tokens))
            ok = value >= minimum
            failures += not ok
            status = "ok" if ok else "FAIL"
            print(f"{theme_name:5} {fg:>26} on {bg:<15} {value:5.2f}:1 (min {minimum}) {status}")
    print(f"{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
