"""Generate placeholder warm podcast LUTs (33^3 .cube files), self-made / CC0.
Math only, no scraped LUT data -> no license ambiguity.
Run: .venv/bin/python tools/make_lut.py
"""
from pathlib import Path

SIZE = 33
OUT_DIR = Path("luts")

VARIANTS = {
    "warm_subtle": 0.5,
    "warm_standard": 1.0,
    "warm_rich": 1.6,
}


def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def skin_mask(r, g, b):
    """Rough skin-tone heuristic (r>g>b, moderate spread) to soften the warm push there."""
    rg = abs((r - g) - 0.15)
    gb = abs((g - b) - 0.10)
    return clamp(1 - rg * 4) * clamp(1 - gb * 4)


def warm_transform(r, g, b, strength):
    mask = skin_mask(r, g, b)
    s = strength * (1 - 0.4 * mask)
    r2 = clamp(r + s * 0.06 * (1 - r))
    g2 = clamp(g + s * 0.01 * (1 - g))
    b2 = clamp(b - s * 0.05 * b)
    return r2, g2, b2


def write_cube(path: Path, strength: float):
    lines = [
        f'TITLE "{path.stem}"',
        f"LUT_3D_SIZE {SIZE}",
        "DOMAIN_MIN 0.0 0.0 0.0",
        "DOMAIN_MAX 1.0 1.0 1.0",
    ]
    step = 1.0 / (SIZE - 1)
    for bi in range(SIZE):
        b = bi * step
        for gi in range(SIZE):
            g = gi * step
            for ri in range(SIZE):
                r = ri * step
                r2, g2, b2 = warm_transform(r, g, b, strength)
                lines.append(f"{r2:.6f} {g2:.6f} {b2:.6f}")
    path.write_text("\n".join(lines) + "\n")


def main():
    OUT_DIR.mkdir(exist_ok=True)
    for name, strength in VARIANTS.items():
        out_path = OUT_DIR / f"{name}.cube"
        write_cube(out_path, strength)
        print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
