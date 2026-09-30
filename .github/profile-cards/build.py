"""Build the profile README artwork in assets/.

Every piece of text is drawn as glyph outlines (Space Grotesk / JetBrains Mono,
the killameep.com fonts), so the SVGs look the same wherever GitHub shows them:
an <img> SVG can't load web fonts. Values mirror killameep.com/assets/css/site.css.

    pip install fonttools brotli uharfbuzz
    python .github/profile-cards/build.py
"""

import math
import pathlib
import random
import re
import urllib.request

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT = ROOT / "assets"
CACHE = HERE / ".cache"

# ---------------------------------------------------------------- tokens

BG = "#07060d"
CARD = "#0f0d1a"          # --surface composited over --bg
LINE = "rgba(196,181,253,0.12)"
LINE_STRONG = "rgba(196,181,253,0.26)"
TEXT = "#ece9f7"
MUTED = "#a29db8"
FAINT = "#6e6987"
VIOLET = "#a78bfa"
VIOLET_DEEP = "#7c3aed"
PINK = "#f472b6"
RADIUS = 14

FONTS = {
    "sans400": "space-grotesk/files/space-grotesk-latin-400-normal.woff2",
    "sans500": "space-grotesk/files/space-grotesk-latin-500-normal.woff2",
    "sans600": "space-grotesk/files/space-grotesk-latin-600-normal.woff2",
    "sans700": "space-grotesk/files/space-grotesk-latin-700-normal.woff2",
    "mono400": "jetbrains-mono/files/jetbrains-mono-latin-400-normal.woff2",
    "mono500": "jetbrains-mono/files/jetbrains-mono-latin-500-normal.woff2",
}


class Font:
    def __init__(self, key, path):
        self.key = key
        CACHE.mkdir(exist_ok=True)
        ttf = CACHE / f"{key}.ttf"
        if not ttf.exists():
            woff2 = CACHE / f"{key}.woff2"
            urllib.request.urlretrieve(f"https://cdn.jsdelivr.net/npm/@fontsource/{path}", woff2)
            f = TTFont(woff2)
            f.flavor = None
            f.save(ttf)
        self.tt = TTFont(ttf)
        self.upm = self.tt["head"].unitsPerEm
        self.order = self.tt.getGlyphOrder()
        self.glyphs = self.tt.getGlyphSet()
        self.hb = hb.Font(hb.Face(ttf.read_bytes()))

    def shape(self, text, size, ls=0.0):
        """Return ([(gid, x_units)], width_px). ls is letter-spacing in em."""
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.hb, buf, {"kern": True, "liga": True})
        out, x = [], 0
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            out.append((info.codepoint, x))
            x += pos.x_advance + ls * self.upm
        return out, x * size / self.upm

    def width(self, text, size, ls=0.0):
        return self.shape(text, size, ls)[1]

    def path(self, gid):
        pen = SVGPathPen(self.glyphs, ntos=lambda v: str(round(v)))
        self.glyphs[self.order[gid]].draw(pen)
        return pen.getCommands()


F = {k: Font(k, p) for k, p in FONTS.items()}


def fmt(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


# ---------------------------------------------------------------- svg doc

class Svg:
    def __init__(self, name, w, h):
        self.name, self.w, self.h = name, w, h
        self.glyph_defs = {}
        self.defs = []
        self.body = []
        self.style = []
        self.rng = random.Random(name)
        self.ids = 0

    def uid(self, p):
        self.ids += 1
        return f"{p}{self.ids}"

    def add(self, s):
        self.body.append(s)

    def glyph_run(self, font, text, x, y, size, ls=0.0):
        """<g> of <use> glyphs with the baseline at (x, y); returns (markup, width)."""
        f = F[font]
        run, width = f.shape(text, size, ls)
        s = size / f.upm
        uses = []
        for gid, gx in run:
            gkey = f"{font}-{gid}"
            if gkey not in self.glyph_defs:
                d = f.path(gid)
                if not d:
                    continue  # spaces
                self.glyph_defs[gkey] = d
            if gkey in self.glyph_defs:
                uses.append(f'<use href="#{gkey}" x="{round(gx)}"/>')
        g = f'<g transform="translate({fmt(x)} {fmt(y)}) scale({s:.5f} {-s:.5f})">{"".join(uses)}</g>'
        return g, width

    def text(self, font, text, x, y, size, fill, ls=0.0, extra=""):
        g, w = self.glyph_run(font, text, x, y, size, ls)
        self.add(f'<g fill="{fill}"{extra}>{g}</g>')
        return w

    def grad_text(self, font, text, x, y, size, ls=0.0, extra=""):
        """Text filled with the site's violet -> pink accent gradient."""
        g, w = self.glyph_run(font, text, x, y, size, ls)
        mid = self.uid("m")
        top, h = y - size * 1.05, size * 1.4
        self.defs.append(
            f'<mask id="{mid}" maskUnits="userSpaceOnUse" x="{fmt(x - 4)}" y="{fmt(top)}" '
            f'width="{fmt(w + 8)}" height="{fmt(h)}"><g fill="#fff">{g}</g></mask>')
        self.add(f'<g{extra}><rect x="{fmt(x - 4)}" y="{fmt(top)}" width="{fmt(w + 8)}" '
                 f'height="{fmt(h)}" fill="url(#accent)" mask="url(#{mid})"/></g>')
        return w

    def arrow(self, x, y, size, color):
        """The site's up-right arrow icon (24px grid), top-left at (x, y)."""
        s = size / 24
        self.add(f'<g transform="translate({fmt(x)} {fmt(y)}) scale({s:.4f})" fill="none" stroke="{color}" '
                 f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                 f'<path d="M7 17 17 7"/><path d="M8 7h9v9"/></g>')

    def stars(self, x, y, w, h, n, dim=1.0):
        out = []
        for _ in range(n):
            sx, sy = x + self.rng.random() * w, y + self.rng.random() * h
            r = 0.35 + self.rng.random() ** 3 * 1.05
            o = (0.25 + self.rng.random() * 0.6) * dim
            cls = self.rng.choice(["t1", "t2", "t3", "", ""])
            c = f' class="{cls}"' if cls else ""
            out.append(f'<circle{c} cx="{fmt(sx)}" cy="{fmt(sy)}" r="{fmt(r)}" opacity="{o:.2f}"/>')
        self.add(f'<g fill="#fff">{"".join(out)}</g>')

    def space(self, x=0, y=0, w=None, h=None, n=None, glow=True):
        """The site's .space background: near-black, soft corner glows and stars."""
        w, h = w or self.w, h or self.h
        cid = self.uid("c")
        self.defs.append(f'<clipPath id="{cid}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{RADIUS}"/></clipPath>')
        self.add(f'<g clip-path="url(#{cid})">')
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{BG}"/>')
        if glow:
            self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="url(#glowV)"/>'
                     f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="url(#glowP)"/>'
                     f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="url(#glowC)"/>')
        self.stars(x, y, w, h, n if n is not None else int(w * h / 2600))
        self.add("</g>")
        self.add(f'<rect x="{x + .5}" y="{y + .5}" width="{w - 1}" height="{h - 1}" rx="{RADIUS - .5}" '
                 f'fill="none" stroke="{LINE}"/>')

    def render(self):
        glyphs = "".join(f'<path id="{k}" d="{d}"/>' for k, d in self.glyph_defs.items())
        css = """
.t1{animation:tw 3.2s ease-in-out infinite alternate}
.t2{animation:tw 4.6s ease-in-out -1.7s infinite alternate}
.t3{animation:tw 6.1s ease-in-out -3.3s infinite alternate}
@keyframes tw{from{opacity:.08}}
.rv{animation:rv .8s cubic-bezier(.2,.7,.2,1) both}
@keyframes rv{from{opacity:0;transform:translateY(10px)}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
""" + "".join(self.style)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{self.name}">'
            f"<style>{' '.join(css.split())}</style><defs>"
            '<linearGradient id="accent" x1="0" y1="0.4" x2="1" y2="0.6">'
            f'<stop offset="0" stop-color="{VIOLET}"/><stop offset="1" stop-color="{PINK}"/></linearGradient>'
            '<radialGradient id="glowV" cx="0.85" cy="0" r="0.6"><stop offset="0" stop-color="#7c3aed" stop-opacity="0.22"/>'
            '<stop offset="0.7" stop-color="#7c3aed" stop-opacity="0"/></radialGradient>'
            '<radialGradient id="glowP" cx="0" cy="1" r="0.5"><stop offset="0" stop-color="#ec4899" stop-opacity="0.12"/>'
            '<stop offset="0.7" stop-color="#ec4899" stop-opacity="0"/></radialGradient>'
            '<radialGradient id="glowC" cx="0.3" cy="0.3" r="0.4"><stop offset="0" stop-color="#67e8f9" stop-opacity="0.05"/>'
            '<stop offset="0.7" stop-color="#67e8f9" stop-opacity="0"/></radialGradient>'
            f"{glyphs}{''.join(self.defs)}</defs>{''.join(self.body)}</svg>"
        )

    def save(self):
        OUT.mkdir(exist_ok=True)
        (OUT / f"{self.name}.svg").write_text(self.render(), encoding="utf-8")
        print(f"assets/{self.name}.svg  {self.w}x{self.h}  {len(self.render()) // 1024} KB")


def wrap(font, text, size, max_w, ls=0.0):
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if cur and F[font].width(trial, size, ls) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + [cur] if cur else lines


def delay(i):
    return f' class="rv" style="animation-delay:{i * 0.07:.2f}s"'


# ---------------------------------------------------------------- pieces

W = 880
HALF = 436          # two cards side by side at width="49.5%"
PAD = 24

STACK = ["Python", "Rust", "TypeScript", "JavaScript", "C#", "PyTorch", "OpenCV", "YOLO",
         "ONNX", "Tauri", "Electron", "Flask", "Docker", "Linux"]


def hero():
    x = 40
    pills = tags_layout(STACK, 12, W - x * 2)
    pills_h = len(pills) * 27 + (len(pills) - 1) * 6
    h = 236 + pills_h + 34
    s = Svg("hero", W, h)
    s.space(n=110)

    w = s.text("mono400", "$ ", x, 52, 14, PINK, extra=delay(0))
    s.text("mono400", "whoami", x + w, 52, 14, FAINT, extra=delay(0))
    label = "killameep.com"
    lw = F["mono400"].width(label, 13)
    s.text("mono400", label, W - x - 21 - lw, 52, 13, VIOLET)
    s.arrow(W - x - 15, 41, 15, VIOLET)

    w = s.text("sans500", "Hi, I’m ", x, 122, 30, MUTED, ls=-0.02, extra=delay(1))
    w += s.grad_text("sans700", "KillaMeep", x + w, 122, 62, ls=-0.045, extra=delay(1))
    s.text("sans700", ".", x + w, 122, 62, TEXT, extra=delay(1))

    # role line: typed out and deleted in a loop, like the homepage
    size, base = 18, 164
    pw = s.text("mono400", ">", x, base, size, PINK, extra=delay(2))
    rx = x + pw + 11
    roles = ["Software Developer", "Process Automation Engineer", "AI Solutions Designer"]
    adv = F["mono400"].width("M", size)
    t, events = 0.6, []           # (time, role index, chars shown)
    for i, r in enumerate(roles):
        for k in range(len(r) + 1):
            events.append((t, i, k))
            t += 0.055
        t += 1.8
        for k in range(len(r) - 1, -1, -1):
            events.append((t, i, k))
            t += 0.028
        t += 0.35
    total = t
    s.add(f'<g{delay(2)}>')
    for i, r in enumerate(roles):
        cid = s.uid("r")
        ev = [(0, 0)] + [(tt, k) for tt, ii, k in events if ii == i]
        kt = ";".join(f"{tt / total:.4f}" for tt, _ in ev)
        vals = ";".join(fmt(k * adv) for _, k in ev)
        s.defs.append(f'<clipPath id="{cid}"><rect x="{fmt(rx)}" y="{base - size}" height="{size * 1.5}" width="0">'
                      f'<animate attributeName="width" dur="{total:.2f}s" repeatCount="indefinite" calcMode="discrete" '
                      f'keyTimes="{kt}" values="{vals}"/></rect></clipPath>')
        g, _ = s.glyph_run("mono400", r, rx, base, size)
        s.add(f'<g fill="{TEXT}" clip-path="url(#{cid})">{g}</g>')
    ev = [(0, 0)] + [(tt, k) for tt, _, k in events]
    kt = ";".join(f"{tt / total:.4f}" for tt, _ in ev)
    vals = ";".join(fmt(rx + k * adv + 3) for _, k in ev)
    s.add(f'<rect class="caret" x="{fmt(rx + 3)}" y="{fmt(base - size * 0.9)}" width="{fmt(size * 0.55)}" '
          f'height="{fmt(size * 1.1)}" fill="{VIOLET}"><animate attributeName="x" dur="{total:.2f}s" '
          f'repeatCount="indefinite" calcMode="discrete" keyTimes="{kt}" values="{vals}"/></rect></g>')
    s.style.append(".caret{animation:blink 1.1s steps(1) infinite}@keyframes blink{50%{opacity:0}}")

    s.text("sans400", "Computer vision, desktop apps, and the glue code that makes boring work disappear.",
           x, 206, 16, MUTED, extra=delay(3))
    s.add(f'<g{delay(4)}>')
    draw_tags(s, pills, x, 236, 12, TEXT, primary=("Python", "Rust"))
    s.add("</g>")
    s.save()


def icon_markup(file, prefix, x, y, size):
    svg = (HERE / "icons" / file).read_text(encoding="utf-8")
    inner = re.sub(r"^.*?<svg[^>]*>|</svg>\s*$", "", svg, flags=re.S)
    inner = re.sub(r'id="([^"]+)"', rf'id="{prefix}\1"', inner)
    inner = re.sub(r'url\(#([^)]+)\)', rf'url(#{prefix}\1)', inner)
    return f'<g transform="translate({x} {y}) scale({size / 512:.5f})">{inner}</g>'


def tags_layout(tags, size, max_w):
    """Rows of (tag, x, width) for .tag pills: 3px/10px padding, 6px gaps."""
    rows, row, x = [], [], 0
    for t in tags:
        w = F["mono400"].width(t, size) + 22
        if row and x + w > max_w:
            rows.append(row)
            row, x = [], 0
        row.append((t, x, w))
        x += w + 6
    return rows + [row]


def draw_tags(s, rows, x, y, size, color, primary=()):
    ph = round(size * 1.65 + 7)
    for r, row in enumerate(rows):
        ty = y + r * (ph + 6)
        for t, tx, w in row:
            hot = t in primary
            fill = "rgba(244,114,182,0.10)" if hot else "rgba(167,139,250,0.07)"
            stroke = "rgba(244,114,182,0.5)" if hot else LINE
            s.add(f'<rect x="{fmt(x + tx + .5)}" y="{fmt(ty + .5)}" width="{fmt(w - 1)}" height="{ph - 1}" '
                  f'rx="{(ph - 1) / 2}" fill="{fill}" stroke="{stroke}"/>')
            s.text("mono400", t, x + tx + 11, ty + ph / 2 + size * 0.36, size, color)
    return len(rows) * ph + (len(rows) - 1) * 6


TAG = 11.5
TAG_H = round(TAG * 1.65 + 7)


def card_metrics(p, w):
    inner = w - PAD * 2
    lines = wrap("sans400", p["text"], 14, min(inner, 740))
    rows = tags_layout(p["tags"], TAG, inner)
    tags_h = len(rows) * TAG_H + (len(rows) - 1) * 6
    return lines, rows, PAD + 36 + 12 + len(lines) * 22 + 14 + tags_h + PAD


def card(p, w, h, index):
    lines, rows, _ = card_metrics(p, w)
    s = Svg(p["file"], w, h)
    cid = s.uid("c")
    s.defs.append(f'<clipPath id="{cid}"><rect width="{w}" height="{h}" rx="{RADIUS}"/></clipPath>')
    s.add(f'<g clip-path="url(#{cid})"><rect width="{w}" height="{h}" fill="{CARD}"/>'
          f'<rect width="{w}" height="{h}" fill="url(#glowV)" opacity="0.6"/>')
    s.stars(0, 0, w, h, int(w * h / 5200), dim=0.35)
    s.add("</g>")
    # border, plus the .card.glow highlight drifting along it
    s.add(f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="{RADIUS - .5}" fill="none" stroke="{LINE}"/>')
    gid = s.uid("g")
    dur = 9 + index * 0.7
    phase = 2.3 * index
    s.defs.append(f'<radialGradient id="{gid}" gradientUnits="userSpaceOnUse" cx="-160" cy="0" r="200">'
                  '<stop offset="0" stop-color="#c4b5fd" stop-opacity="0.6"/><stop offset="1" stop-color="#c4b5fd" stop-opacity="0"/>'
                  f'<animate attributeName="cx" values="-200;{w + 200}" dur="{dur}s" begin="-{phase}s" repeatCount="indefinite"/>'
                  f'<animate attributeName="cy" values="0;{h * 0.35:.0f};0" dur="{dur * 1.6:.1f}s" begin="-{phase}s" repeatCount="indefinite"/>'
                  "</radialGradient>")
    s.add(f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="{RADIUS - .5}" fill="none" stroke="url(#{gid})"/>')

    mid = PAD + 18          # centre line of the header row
    tx = PAD
    if p.get("icon"):
        s.add(icon_markup(p["icon"], p["file"] + "-", PAD, PAD, 36))
        tx += 36 + 12
    size = 22 if p.get("featured") else 20
    s.text("sans600", p["name"], tx, mid + size * 0.36, size, TEXT, ls=-0.02)
    lw = F["mono400"].width("source", 13)
    ax = w - PAD - 14
    s.text("mono400", "source", ax - 6 - lw, mid + 4.5, 13, VIOLET)
    s.arrow(ax, mid - 7, 14, VIOLET)

    y = PAD + 36 + 12
    for i, line in enumerate(lines):
        s.text("sans400", line, PAD, y + 15 + i * 22, 14, MUTED)
    tags_h = len(rows) * TAG_H + (len(rows) - 1) * 6
    draw_tags(s, rows, PAD, h - PAD - tags_h, TAG, MUTED)
    s.save()


PROJECTS = [
    dict(file="card-waypoint", name="Waypoint", icon="waypoint.svg", featured=True,
         text="Free, open-source image geolocation. Give it one outdoor photo and it estimates where on Earth "
              "it was taken, using a diffusion model, sun position and street-level matching on an interactive "
              "map. Runs on a native Rust engine, no Python needed.",
         tags=["Tauri", "Rust", "ONNX Runtime", "OSINT", "LightGlue"]),
    dict(file="card-glyphify", name="Glyphify", icon="glyphify.svg",
         text="Turns images and videos into ASCII art: color or grayscale, braille and custom character sets, "
              "live tuning, export to TXT, HTML, PNG or GIF.",
         tags=["Electron", "JavaScript", "FFmpeg"]),
    dict(file="card-beatblock", name="BeatBlock AI",
         text="Real-time YOLOv5 object detection for the rhythm game BeatBlock, spotting in-game elements "
              "with low latency for gameplay analysis.",
         tags=["Python", "YOLOv5", "Computer vision"]),
    dict(file="card-astrospheric", name="Astrospheric for HA",
         text="Home Assistant integration for Astrospheric astronomy weather: seeing, transparency and cloud "
              "sensors, plus custom Lovelace cards.",
         tags=["Home Assistant", "TypeScript", "HACS"]),
    dict(file="card-multigpu", name="Multi-GPU Batch",
         text="AUTOMATIC1111 extension that splits image generation across all your GPUs in parallel and "
              "hands back one merged result.",
         tags=["Python", "Stable Diffusion", "A1111"]),
]


if __name__ == "__main__":
    hero()
    feat, *rest = PROJECTS
    card(feat, W, math.ceil(card_metrics(feat, W)[-1]), 0)
    for i in range(0, len(rest), 2):
        pair = rest[i:i + 2]
        h = math.ceil(max(card_metrics(p, HALF)[-1] for p in pair))
        for j, p in enumerate(pair):
            card(p, HALF, h, i + j + 1)

