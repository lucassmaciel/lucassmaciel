"""Build the profile hero SVGs (light + dark).

Text is shaped with HarfBuzz and converted to outlines, so the typography
renders identically on GitHub without loading any font.

    uv run --with fonttools --with uharfbuzz scripts/build_hero.py path/to/Archivo[wdth,wght].ttf
"""

import sys
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen

W, H = 880, 340

THEMES = {
    "light": {
        "ink": "#24150E",       # Rio Negro
        "muted": "#6B4430",     # strong tea
        "negro": "#3A2418",     # stream A
        "solimoes": "#B8935F",  # stream B
        "node": "#FBF8F3",
        "line": "#D9CBB6",
        "ok": "#3F8A5C",
        "queued": "#B9A891",
    },
    "dark": {
        "ink": "#EFE9DF",
        "muted": "#B39B86",
        "negro": "#8E6B55",
        "solimoes": "#D9BC8F",
        "node": "#161B22",
        "line": "#3A3128",
        "ok": "#5DB07E",
        "queued": "#6E6153",
    },
}


class Typesetter:
    def __init__(self, font_path: str):
        blob = hb.Blob.from_file_path(font_path)
        self.face = hb.Face(blob)
        self.upem = self.face.upem
        self.glyphs = {}  # (gid, wdth, wght) -> (id, d); each outline is defined once

    def defs(self) -> str:
        return "".join(f'<path id="{gid}" d="{d}"/>' for gid, d in self.glyphs.values())

    def _glyph(self, font, gid, wdth, wght):
        key = (gid, wdth, wght)
        if key not in self.glyphs:
            pen = SVGPathPen(None, ntos=lambda v: f"{round(v)}")
            font.draw_glyph_with_pen(gid, pen)
            d = pen.getCommands()
            self.glyphs[key] = (f"g{len(self.glyphs)}", d) if d else (None, "")
        return self.glyphs[key][0]

    def path(self, text, size, x, y, wdth=100, wght=400, track=0.0, anchor="start"):
        if not text:
            return "", 0.0
        font = hb.Font(self.face)
        font.set_variations({"wdth": wdth, "wght": wght})
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(font, buf, {"kern": True, "liga": True})

        scale = size / self.upem
        track_units = track * self.upem
        total = sum(p.x_advance + track_units for p in buf.glyph_positions) - track_units
        if anchor == "end":
            x -= total * scale
        elif anchor == "middle":
            x -= total * scale / 2

        parts, cursor = [], 0.0
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            gid = self._glyph(font, info.codepoint, wdth, wght)
            if gid:
                gx = x + (cursor + pos.x_offset) * scale
                gy = y - pos.y_offset * scale
                parts.append(
                    f'<use href="#{gid}" transform="translate({gx:.1f} {gy:.1f}) scale({scale:.5f} {-scale:.5f})"/>'
                )
            cursor += pos.x_advance + track_units
        return "".join(parts), total * scale


def node(ts, t, x, y, w, title, role, years, state, delay):
    h = 66
    stroke = t["line"]
    dot = t["ok"] if state == "ok" else t["queued"]
    dash = ' stroke-dasharray="4 4"' if state == "queued" else ""
    # A node with no role line centres its title and status dot vertically.
    title_y, dot_y = (y + 27, y + 21.5) if role else (y + 39, y + 33)
    name, _ = ts.path(title, 17, x + 34, title_y, wdth=80, wght=650)
    sub, _ = ts.path(role, 13.5, x + 34, y + 46, wdth=75, wght=420)
    yrs, _ = ts.path(years, 12.5, x + w - 14, y + 27, wdth=75, wght=420, anchor="end")
    status = (
        f'<circle class="dot" style="animation-delay:{delay}s" cx="{x + 18}" cy="{dot_y}" r="5" fill="{dot}"/>'
        if state == "ok"
        else f'<circle cx="{x + 18}" cy="{dot_y}" r="4.25" fill="none" stroke="{dot}" stroke-width="1.5"/>'
    )
    return (
        f'<g><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="7" fill="{t["node"]}" stroke="{stroke}"{dash}/>'
        f'{status}<g fill="{t["ink"]}">{name}</g><g fill="{t["muted"]}">{sub}{yrs}</g></g>'
    )


def build(ts: Typesetter, theme: str) -> str:
    t = THEMES[theme]

    name, _ = ts.path("Lucas Maciel", 62, 20, 78, wdth=125, wght=760, track=-0.012)
    tagline, _ = ts.path(
        "Data engineer in Manaus. I move data from where it lands to where it’s useful.",
        17, 22, 114, wdth=88, wght=400,
    )

    ax, ay = 20, 160   # Calidus
    bx, by = 20, 254   # Sidia
    mx, my = 372, 207  # EloGroup
    nx, ny = 742, 207  # next
    nw = 236
    cy_a, cy_b, cy_m = ay + 33, by + 33, my + 33

    # Two upstream branches meet at the EloGroup node; downstream they keep
    # running side by side without mixing, like the Negro and the Solimões.
    edges = (
        f'<path class="edge" style="animation-delay:.35s" d="M{ax + nw} {cy_a} C{ax + nw + 70} {cy_a} {mx - 70} {cy_m - 6} {mx} {cy_m - 6}" '
        f'stroke="{t["negro"]}"/>'
        f'<path class="edge" style="animation-delay:.5s" d="M{bx + nw} {cy_b} C{bx + nw + 70} {cy_b} {mx - 70} {cy_m + 6} {mx} {cy_m + 6}" '
        f'stroke="{t["solimoes"]}"/>'
        f'<path class="edge" style="animation-delay:1.25s;stroke-width:3;stroke-linecap:butt" d="M{mx + nw} {cy_m - 1.5} H{nx - 34}" stroke="{t["negro"]}"/>'
        f'<path class="edge" style="animation-delay:1.25s;stroke-width:3;stroke-linecap:butt" d="M{mx + nw} {cy_m + 1.5} H{nx - 34}" stroke="{t["solimoes"]}"/>'
        f'<path d="M{nx - 30} {cy_m} H{nx}" stroke="{t["queued"]}" stroke-dasharray="3 4"/>'
    )

    nodes = (
        node(ts, t, ax, ay, nw, "Calidus", "Computer vision R&D lead", "2024–25", "ok", 0.2)
        + node(ts, t, bx, by, nw, "Sidia", "Python and Polars pipelines", "2025–26", "ok", 0.3)
        + node(ts, t, mx, my, nw, "EloGroup", "Spark, Airflow, Iceberg", "2026–", "ok", 1.1)
        + node(ts, t, nx, my, 104, "Next", "", "", "queued", 0)
    )

    style = f"""
    .edge {{ fill: none; stroke-width: 2.25; stroke-linecap: round;
             stroke-dasharray: 400; stroke-dashoffset: 0;
             animation: draw .7s cubic-bezier(.3,.6,.2,1) backwards; }}
    .dot {{ animation: run .45s ease-out backwards; }}
    @keyframes draw {{ from {{ stroke-dashoffset: 400; }} }}
    @keyframes run {{ from {{ fill: {t["queued"]}; r: 3; }} }}
    @media (prefers-reduced-motion: reduce) {{ .edge, .dot {{ animation: none; }} }}
    """

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
        f'aria-labelledby="t d">'
        f'<title id="t">Lucas Maciel, data engineer</title>'
        f'<desc id="d">Career drawn as a pipeline: Calidus (computer vision R&amp;D, 2024–25) and Sidia '
        f'(Python and Polars pipelines, 2025–26) run in parallel and merge into EloGroup (Spark, Airflow, '
        f'Iceberg, 2026–), which flows on to what is next.</desc>'
        f"<style>{style}</style><defs>{ts.defs()}</defs>"
        f'<g fill="{t["ink"]}">{name}</g><g fill="{t["muted"]}">{tagline}</g>'
        f"{edges}{nodes}</svg>"
    )


def main():
    font_path = sys.argv[1]
    out = Path(__file__).resolve().parent.parent / "assets"
    out.mkdir(exist_ok=True)
    ts = Typesetter(font_path)
    for theme in THEMES:
        (out / f"hero-{theme}.svg").write_text(build(ts, theme), encoding="utf-8")
        print(f"wrote assets/hero-{theme}.svg")


if __name__ == "__main__":
    main()
