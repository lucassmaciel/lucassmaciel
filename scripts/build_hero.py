"""Build the profile hero SVGs (light + dark).

The name is cut into horizontal bands, like a table split into partitions.
On load the bands arrive out of line and settle into place once; the thin
cuts between them stay visible in the final, static state. Below it, the
career is drawn as a DAG: two parallel upstream tasks merge into the current one.

Text is shaped with HarfBuzz and converted to outlines, so the typography
renders identically on GitHub without loading any font.

    uv run --with fonttools --with uharfbuzz scripts/build_hero.py path/to/Archivo[wdth,wght].ttf
"""

import sys
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

W, H = 880, 362
PAD = 20

NAME = "Lucas Maciel"
LINE = "Data engineer building batch pipelines with Spark, Airflow and Iceberg."

CUTS = [0.25, 0.5, 0.66]  # where the partitions split, as a fraction of the name's height
GAP = 1.6          # visible cut between bands, px
# Where each band starts before settling: alternating, uneven, never random.
OFFSETS = [-44, 28, -16, 36]

THEMES = {
    "light": {
        "ink": "#24150E", "muted": "#6B4430",           # Rio Negro, strong tea
        "negro": "#3A2418", "solimoes": "#B8935F",      # the two rivers, as edges
        "node": "#FBF8F3", "line": "#D9CBB6", "ok": "#3F8A5C", "queued": "#B9A891",
    },
    "dark": {
        "ink": "#EFE9DF", "muted": "#B39B86",
        "negro": "#8E6B55", "solimoes": "#D9BC8F",
        "node": "#161B22", "line": "#3A3128", "ok": "#5DB07E", "queued": "#6E6153",
    },
}


class Typesetter:
    def __init__(self, font_path: str):
        blob = hb.Blob.from_file_path(font_path)
        self.face = hb.Face(blob)
        self.upem = self.face.upem
        tt = TTFont(font_path)
        self.cap_height = tt["OS/2"].sCapHeight / self.upem
        self.ascender = tt["OS/2"].sTypoAscender / self.upem
        self.glyphs = {}  # (gid, wdth, wght) -> (id, d); each outline is defined once

    def defs(self) -> str:
        return "".join(f'<path id="{gid}" d="{d}"/>' for gid, d in self.glyphs.values() if gid)

    def _glyph(self, font, gid, wdth, wght):
        key = (gid, wdth, wght)
        if key not in self.glyphs:
            pen = SVGPathPen(None, ntos=lambda v: f"{round(v)}")
            font.draw_glyph_with_pen(gid, pen)
            d = pen.getCommands()
            self.glyphs[key] = (f"g{len(self.glyphs)}", d) if d else (None, "")
        return self.glyphs[key][0]

    def _shape(self, text, wdth, wght):
        font = hb.Font(self.face)
        font.set_variations({"wdth": wdth, "wght": wght})
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(font, buf, {"kern": True, "liga": True})
        return font, buf

    def ink(self, text, wdth=100, wght=400):
        """Top and bottom of the actual outlines, in em, measured from the baseline."""
        font, buf = self._shape(text, wdth, wght)
        tops, bottoms = [], []
        for info in buf.glyph_infos:
            e = font.get_glyph_extents(info.codepoint)
            if e and e.height:
                tops.append(e.y_bearing)
                bottoms.append(e.y_bearing + e.height)
        return max(tops) / self.upem, min(bottoms) / self.upem

    def width(self, text, size, wdth=100, wght=400, track=0.0):
        _, buf = self._shape(text, wdth, wght)
        adv = sum(p.x_advance for p in buf.glyph_positions)
        return (adv + track * self.upem * (len(buf.glyph_positions) - 1)) * size / self.upem

    def path(self, text, size, x, y, wdth=100, wght=400, track=0.0, anchor="start"):
        if not text:
            return ""
        if anchor == "end":
            x -= self.width(text, size, wdth, wght, track)
        font, buf = self._shape(text, wdth, wght)
        scale = size / self.upem
        track_units = track * self.upem
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
        return "".join(parts)


def node(ts, t, x, y, w, title, role, years, state, delay):
    h = 66
    dot = t["ok"] if state == "ok" else t["queued"]
    dash = ' stroke-dasharray="4 4"' if state == "queued" else ""
    # A node with no role line centres its title and status dot vertically.
    title_y, dot_y = (y + 27, y + 21.5) if role else (y + 39, y + 33)
    name = ts.path(title, 17, x + 34, title_y, wdth=80, wght=650)
    sub = ts.path(role, 13.5, x + 34, y + 46, wdth=75, wght=420)
    yrs = ts.path(years, 12.5, x + w - 14, y + 27, wdth=75, wght=420, anchor="end")
    status = (
        f'<circle class="dot" style="animation-delay:{delay}s" cx="{x + 18}" cy="{dot_y}" r="5" fill="{dot}"/>'
        if state == "ok"
        else f'<circle cx="{x + 18}" cy="{dot_y}" r="4.25" fill="none" stroke="{dot}" stroke-width="1.5"/>'
    )
    return (
        f'<g><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="7" fill="{t["node"]}" stroke="{t["line"]}"{dash}/>'
        f'{status}<g fill="{t["ink"]}">{name}</g><g fill="{t["muted"]}">{sub}{yrs}</g></g>'
    )


def dag(ts, t, top):
    """Calidus and Sidia ran in parallel and merge into EloGroup; downstream the
    two streams keep running side by side, like the Negro and the Solimões."""
    nw = 236
    ax, ay = PAD, top
    bx, by = PAD, top + 94
    mx, my = 372, top + 47
    nx = W - PAD - 104  # right edge lines up with the end of the name
    cy_a, cy_b, cy_m = ay + 33, by + 33, my + 33
    edges = (
        f'<path class="edge" style="animation-delay:.95s" d="M{ax + nw} {cy_a} C{ax + nw + 70} {cy_a} {mx - 70} {cy_m - 6} {mx} {cy_m - 6}" stroke="{t["negro"]}"/>'
        f'<path class="edge" style="animation-delay:1.1s" d="M{bx + nw} {cy_b} C{bx + nw + 70} {cy_b} {mx - 70} {cy_m + 6} {mx} {cy_m + 6}" stroke="{t["solimoes"]}"/>'
        f'<path class="edge" style="animation-delay:1.85s;stroke-width:3;stroke-linecap:butt" d="M{mx + nw} {cy_m - 1.5} H{nx - 34}" stroke="{t["negro"]}"/>'
        f'<path class="edge" style="animation-delay:1.85s;stroke-width:3;stroke-linecap:butt" d="M{mx + nw} {cy_m + 1.5} H{nx - 34}" stroke="{t["solimoes"]}"/>'
        f'<path d="M{nx - 30} {cy_m} H{nx}" stroke="{t["queued"]}" stroke-dasharray="3 4"/>'
    )
    nodes = (
        node(ts, t, ax, ay, nw, "Calidus", "Computer vision R&D lead", "2024–25", "ok", 0.8)
        + node(ts, t, bx, by, nw, "Sidia", "Python and Polars pipelines", "2025–26", "ok", 0.9)
        + node(ts, t, mx, my, nw, "EloGroup", "Spark, Airflow, Iceberg", "2026–", "ok", 1.7)
        + node(ts, t, nx, my, 104, "Next", "", "", "queued", 0)
    )
    return edges + nodes


def build(ts: Typesetter, theme: str) -> str:
    t = THEMES[theme]

    # Fit the name to the full width.
    wdth, wght, track = 118, 820, -0.018
    size = (W - 2 * PAD) / ts.width(NAME, 1, wdth, wght, track)
    ink_top, ink_bottom = ts.ink(NAME, wdth, wght)
    baseline = PAD + size * ink_top
    top = baseline - size * ink_top
    bottom = baseline - size * ink_bottom

    name = ts.path(NAME, size, PAD, baseline, wdth, wght, track)
    line = ts.path(LINE, 18.5, PAD + 2, baseline + 44, wdth=92, wght=420)
    graph = dag(ts, t, baseline + 84)

    edges = [top] + [top + c * (bottom - top) for c in CUTS] + [bottom]
    clips, bands = [], []
    for i in range(len(edges) - 1):
        y0 = edges[i] + (GAP / 2 if i else 0)
        y1 = edges[i + 1] - (GAP / 2 if i < len(edges) - 2 else 0)
        clips.append(
            f'<clipPath id="b{i}"><rect x="0" y="{y0:.2f}" width="{W}" height="{y1 - y0:.2f}"/></clipPath>'
        )
        bands.append(
            f'<g class="band" style="--from:{OFFSETS[i]}px;animation-delay:{0.08 * i:.2f}s">'
            f'<use href="#name" clip-path="url(#b{i})"/></g>'
        )

    style = """
    .band { animation: settle 1.1s cubic-bezier(.16,1,.3,1) backwards; }
    .edge { fill: none; stroke-width: 2.25; stroke-linecap: round; stroke-dasharray: 400;
            animation: draw .7s cubic-bezier(.3,.6,.2,1) backwards; }
    .dot { animation: run .45s ease-out backwards; }
    @keyframes settle { from { transform: translateX(var(--from)); opacity: .35; } }
    @keyframes draw { from { stroke-dashoffset: 400; } }
    @keyframes run { from { fill: QUEUED; r: 3; } }
    @media (prefers-reduced-motion: reduce) { .band, .edge, .dot { animation: none; } }
    """.replace("QUEUED", t["queued"])

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
        f'role="img" aria-labelledby="t">'
        f'<title id="t">Lucas Maciel. {LINE}</title>'
        f'<desc>Career as a pipeline: Calidus (computer vision R&amp;D, 2024–25) and Sidia (Python and Polars '
        f'pipelines, 2025–26) run in parallel and merge into EloGroup (Spark, Airflow, Iceberg, 2026–).</desc>'
        f"<style>{style}</style>"
        f'<defs>{ts.defs()}<g id="name">{name}</g>{"".join(clips)}</defs>'
        f'<g fill="{t["ink"]}">{"".join(bands)}</g>'
        f'<g fill="{t["muted"]}">{line}</g>'
        f"{graph}</svg>"
    )


def main():
    font_path = sys.argv[1]
    out = Path(__file__).resolve().parent.parent / "assets"
    out.mkdir(exist_ok=True)
    for theme in THEMES:
        ts = Typesetter(font_path)  # fresh glyph table per file
        (out / f"hero-{theme}.svg").write_text(build(ts, theme), encoding="utf-8")
        print(f"wrote assets/hero-{theme}.svg")


if __name__ == "__main__":
    main()
