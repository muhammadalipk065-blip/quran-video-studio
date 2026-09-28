#!/usr/bin/env python3
"""
Quran Recitation + Translation Video Generator
==============================================
Generates a polished recitation video for any surah:

    python recitation_video.py --surah 112
    python recitation_video.py --surah 112 --vertical --verses 2   # one-verse Short
    python recitation_video.py --surah 36 --reciter Husary_128kbps --translation 22

Pipeline
--------
1. Arabic (Uthmani) text + English translation  <- api.quran.com (free API)
2. Per-verse human recitation audio             <- everyayah.com verse MP3s
3. Renders 16:9 (long-form) or 9:16 (Shorts) MP4 with moviepy + PIL.

Sources / licensing notes
-------------------------
- api.quran.com is a free public API. Translation texts belong to their
  translators/publishers -- check reuse terms for your chosen translation
  before monetising. Saheeh International (20, default) is widely reused;
  Pickthall (19) is public domain.
- everyayah.com hosts per-verse recitation MP3s from established qurra.
  Credit the reciter on screen (done automatically) and respect the site's
  terms of use.

Requires: the venv in this folder (see README.md).
"""

import argparse
import json
import os
import re
import sys
import unicodedata

import requests
from PIL import Image, ImageDraw, ImageFont
from PIL import features as _pil_features

# Pillow wheels for some interpreters (notably CPython 3.14) are built
# without libraqm, in which case ``direction="rtl"`` raises ValueError.
# Detect once; QRV_NO_RAQM=1 forces the fallback path for testing.
HAS_RAQM = _pil_features.check("raqm") and os.environ.get("QRV_NO_RAQM") != "1"
# Kwargs enabling RTL shaping at draw time -- only valid with libraqm.
RTL = {"direction": "rtl"} if HAS_RAQM else {}

# KFGQPC Uthmanic Hafs: the authentic Madani mushaf typeface (King Fahd
# Glorious Quran Printing Complex). Rendered with HarfBuzz shaping +
# FreeType rasterisation (see below) so diacritics, ligatures and marks
# sit exactly as in the printed mushaf.
try:
    import uharfbuzz as _hb
    import freetype as _ft
    _HB_DEPS = True
except Exception:  # optional dependency: fall back to Pillow/reshaper paths
    _hb = _ft = None
    _HB_DEPS = False


# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_AR = os.path.join(BASE_DIR, "assets", "fonts", "AmiriQuran-Regular.ttf")
FONT_AR_HB = os.path.join(BASE_DIR, "assets", "fonts", "KFGQPC-Hafs.ttf")
HAS_HB = _HB_DEPS and os.path.exists(FONT_AR_HB)
# Fallback Arabic fonts for environments without libraqm: unlike Amiri
# Quran these carry Arabic presentation forms, so pre-shaped text
# renders. Noto Naskh Arabic is a proper mushaf-style naskh;
# FreeSerif is kept as a last resort.
FONT_AR_FALLBACK = os.path.join(BASE_DIR, "assets", "fonts", "NotoNaskhArabic.ttf")
FONT_AR_FALLBACK2 = os.path.join(BASE_DIR, "assets", "fonts", "FreeSerif.ttf")
ASSETS = os.path.join(BASE_DIR, "assets")
BG_DIR = os.path.join(ASSETS, "backgrounds")
DEFAULT_BG = os.path.join(BG_DIR, "bg-geometric.jpg")

QURAN_API = "https://api.quran.com/api/v4"
EVERYAYAH = "https://everyayah.com/data"

RECITERS = {
    "Alafasy_128kbps": "Mishary Rashid Alafasy",
    "Abdul_Basit_Murattal_192kbps": "AbdulBasit AbdulSamad",
    "Husary_128kbps": "Mahmoud Khalil Al-Husary",
    "Minshawy_Murattal_128kbps": "Mohamed Siddiq Al-Minshawi",
    "Saood_ash-Shuraym_128kbps": "Saood ash-Shuraym",
}

TRANSLATIONS = {
    20: "Saheeh International",
    22: "Abdullah Yusuf Ali",
    19: "M. Marmaduke Pickthall (public domain)",
    85: "Abdul Haleem",
    203: "Al-Hilali & Muhsin Khan",
    158: "Dr. Israr Ahmad (Bayan-ul-Quran)",
}

BISMILLAH_AR = "بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ"
BISMILLAH_EN = "In the name of Allah, the Entirely Merciful, the Especially Merciful."

# Palette
BG = (11, 24, 38)          # deep navy
GOLD = (201, 162, 75)      # muted gold
CREAM = (245, 239, 224)    # warm white for Arabic
GREY = (176, 183, 196)     # muted grey for translation
DIM = (120, 128, 142)      # dimmest for credits

AR_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def latin_font(size):
    for name in ("DejaVuSans.ttf", "DejaVuSansCondensed.ttf", "arial.ttf"):
        for d in ("/usr/share/fonts/truetype/dejavu",
                  "/usr/share/fonts", "C:/Windows/Fonts"):
            p = os.path.join(d, name)
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def arabic_font(size):
    """Amiri Quran when libraqm shaping is available, else a naskh
    fallback (which carries the Arabic presentation forms the reshaper
    needs).

    The fallback path draws pre-shaped visual-order text, so it forces
    Pillow's BASIC layout engine: on Pillow builds that *do* ship raqm
    (e.g. local dev machines) the default engine would otherwise apply
    the bidi algorithm a second time and mirror the line.
    """
    if HAS_RAQM:
        paths = (FONT_AR,)
        engine = {}
    else:
        paths = (FONT_AR_FALLBACK, FONT_AR_FALLBACK2, FONT_AR)
        engine = {"layout_engine": ImageFont.Layout.BASIC}
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size, **engine)
    return ImageFont.load_default()


def shape_arabic(text):
    """Return display-ready Arabic text.

    With libraqm the logical-order text is returned unchanged and shaped
    at draw time via Pillow ``direction="rtl"`` with the Amiri Quran
    font -- do NOT pre-shape in that case (its presentation forms would
    render as tofu boxes). Without libraqm, pre-shape to visual order
    with arabic_reshaper + python-bidi; draw without ``direction``.
    """
    if HAS_RAQM:
        return text
    from arabic_reshaper import ArabicReshaper
    from bidi.algorithm import get_display
    reshaper = ArabicReshaper(
        configuration={"delete_harakat": False, "support_ligatures": True})
    return get_display(reshaper.reshape(text))


# ----------------------------------------------------------------------------
# Mushaf-quality Arabic rendering (HarfBuzz + FreeType)
# ----------------------------------------------------------------------------
# Pillow without libraqm cannot shape Arabic at all, and arabic_reshaper
# only works with fonts that carry Arabic presentation forms -- which the
# Madani mushaf typeface does not. So the primary renderer shapes with
# HarfBuzz (real OpenType shaping: contextual forms, ligatures, mark
# positioning) via uharfbuzz and rasterises each glyph with freetype-py.
# Both are pure wheels: they work on Streamlit Cloud with no system
# libraries, giving identical output locally and hosted.
_hb_cache = {}


def _hb_shaped(text, size):
    """Shape Arabic text with HarfBuzz.

    Returns (glyph_infos, glyph_positions, total_advance_px, ft_face).
    HarfBuzz returns glyphs in left-to-right *visual* order with final
    advances -- bidi reordering is already done, so the caller simply
    draws the glyphs left to right, advancing the pen by x_advance.
    """
    if size not in _hb_cache:
        blob = _hb.Blob.from_file_path(FONT_AR_HB)
        hbf = _hb.Font(_hb.Face(blob))
        hbf.scale = (size * 64, size * 64)
        ftf = _ft.Face(FONT_AR_HB)
        ftf.set_char_size(size * 64)
        _hb_cache[size] = (hbf, ftf)
    hbf, ftf = _hb_cache[size]
    buf = _hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    _hb.shape(hbf, buf, {"kern": True, "liga": True})
    infos, poss = buf.glyph_infos, buf.glyph_positions
    # uharfbuzz returns None for positions on empty text.
    infos = infos or []
    poss = poss or []
    total = sum(p.x_advance for p in poss) / 64.0
    return infos, poss, total, ftf


def hb_text_width(text, size):
    """Pixel width of Arabic text in the mushaf font (used for wrapping)."""
    _, _, total, _ = _hb_shaped(text, size)
    return abs(total)


def hb_render_line(text, size, fill, stroke=False):
    """Render one Arabic line with the mushaf font.

    Returns a tightly cropped RGBA image of the ink, ready to paste.
    Glyphs come from HarfBuzz in left-to-right visual order and are
    drawn that way; the bidi reordering is already baked in.
    """
    from PIL import ImageChops, ImageFilter
    if not text.strip():
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    infos, poss, total, ftf = _hb_shaped(text, size)
    pad = int(size * 0.6)
    W = int(abs(total)) + pad * 2
    H = int(size * 2.8)
    mask = Image.new("L", (W, H), 0)
    baseline = int(H * 0.60)
    pen = pad
    x0, x1, y0, y1 = W, 0, H, 0
    for gi, gp in zip(infos, poss):
        adv = gp.x_advance / 64.0
        gx = pen + gp.x_offset / 64.0
        ftf.load_glyph(gi.codepoint,
                       _ft.FT_LOAD_RENDER | _ft.FT_LOAD_TARGET_NORMAL)
        bmp = ftf.glyph.bitmap
        w, h = bmp.width, bmp.rows
        if w and h:
            left = int(gx + ftf.glyph.bitmap_left)
            # HarfBuzz y grows up, PIL y grows down -> negate y_offset.
            top = int(baseline - ftf.glyph.bitmap_top - gp.y_offset / 64.0)
            gimg = Image.frombytes("L", (w, h), bytes(bmp.buffer))
            tmp = Image.new("L", (W, H), 0)
            tmp.paste(gimg, (left, top))
            mask = ImageChops.lighter(mask, tmp)
            x0, x1 = min(x0, left), max(x1, left + w)
            y0, y1 = min(y0, top), max(y1, top + h)
        pen += adv
    cpad = max(4, int(size * 0.12))
    box = (max(0, x0 - cpad), max(0, y0 - cpad),
           min(W, x1 + cpad), min(H, y1 + cpad))
    if box[2] <= box[0] or box[3] <= box[1]:
        box = (0, 0, W, H)
    mask_c = mask.crop(box)
    img = Image.new("RGBA", mask_c.size, (0, 0, 0, 0))
    if stroke:
        sm = mask_c.filter(ImageFilter.MaxFilter(7))
        img.paste((0, 0, 0, 255), (0, 0), sm)
    img.paste(Image.new("RGBA", mask_c.size, fill + (255,)), (0, 0), mask_c)
    return img


def wrap_arabic_hb(text, size, max_w):
    """Greedy word wrap measured with the mushaf font."""
    lines, cur = [], ""
    for w in text.split(" "):
        t = (cur + " " + w).strip()
        if hb_text_width(t, size) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def paste_line(img, line_img, cx, y_top):
    """Paste a rendered Arabic line centred on cx, top edge at y_top."""
    x, y = int(cx - line_img.width / 2), int(y_top)
    if img.mode == "RGBA":
        img.alpha_composite(line_img, (x, y))
    else:
        img.paste(line_img, (x, y), line_img)


def with_verse_ornament(text, n):
    indic = str(n).translate(AR_DIGITS)
    # The KFGQPC mushaf font renders Arabic-Indic digits inside the
    # traditional ayah-end medallion on its own (multi-digit numbers
    # share one medallion), so no extra mark character is needed. The
    # non-breaking space keeps the ornament glued to the last word
    # when wrapping.
    return f"{text}\u00A0{indic}"


def strip_html(text):
    text = re.sub(r"<sup[^>]*>.*?</sup>", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def api_get(path, params=None):
    r = requests.get(QURAN_API + path, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def download(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return dest
    r = requests.get(url, stream=True, timeout=60)
    r.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in r.iter_content(65536):
            f.write(chunk)
    return dest


def wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= max_w:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


# ----------------------------------------------------------------------------
# Data fetching
# ----------------------------------------------------------------------------

def fetch_surah(surah_no, reciter, translation_id):
    surah_dir = os.path.join(ASSETS, f"s{surah_no:03d}_{reciter}")
    os.makedirs(surah_dir, exist_ok=True)

    ch = api_get(f"/chapters/{surah_no}")["chapter"]
    verses = api_get("/quran/verses/uthmani",
                     {"chapter_number": surah_no})["verses"]
    trans = api_get(f"/quran/translations/{translation_id}",
                    {"chapter_number": surah_no})["translations"]

    items = []
    if ch["bismillah_pre"] and surah_no not in (1, 9):
        items.append({
            "key": "bismillah", "n": 0,
            "arabic": BISMILLAH_AR, "english": BISMILLAH_EN,
            "audio": download(f"{EVERYAYAH}/{reciter}/001001.mp3",
                              os.path.join(surah_dir, "bismillah.mp3")),
        })

    for v, t in zip(verses, trans):
        s_no, v_no = v["verse_key"].split(":")
        items.append({
            "key": v["verse_key"], "n": int(v_no),
            "arabic": with_verse_ornament(v["text_uthmani"], int(v_no)),
            "english": strip_html(t["text"]),
            "audio": download(
                f"{EVERYAYAH}/{reciter}/{int(s_no):03d}{int(v_no):03d}.mp3",
                os.path.join(surah_dir, f"{int(v_no):03d}.mp3")),
        })
    return ch, items


# ----------------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------------

def draw_frame(W, H, header, arabic, english, footer, vertical=False,
               transparent=False):
    # transparent=True -> RGBA card with no backdrop, for compositing over
    # a background image/video. Adds a text stroke for readability.
    img = Image.new("RGBA" if transparent else "RGB",
                    (W, H), (0, 0, 0, 0) if transparent else BG)
    d = ImageDraw.Draw(img)
    stroke = {"stroke_width": 2, "stroke_fill": (0, 0, 0)} if transparent else {}

    # thin gold frame
    m = 28 if not vertical else 22
    d.rectangle([m, m, W - m, H - m], outline=GOLD, width=2)

    cx = W // 2
    max_w = W - 260 if not vertical else W - 140

    def wrap_arabic(f_ar):
        lines, cur = [], ""
        for w in arabic.split(" "):
            t = (cur + " " + w).strip()
            if d.textlength(shape_arabic(t), font=f_ar, **RTL) <= max_w or not cur:
                cur = t
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    if vertical:
        # Vertical (Shorts) layout: the whole content block (header +
        # Arabic + translation) is vertically centred in the frame so
        # there is no large empty band at the bottom. Arabic auto-sizes
        # down from 100pt until every wrapped line fits max_w.
        f_head = latin_font(44)
        f_en = latin_font(46)
        f_foot = latin_font(34)
        ar_size = 100
        if HAS_HB:
            # Mushaf font path: wrap and measure with HarfBuzz shaping.
            while True:
                ar_lines = wrap_arabic_hb(arabic, ar_size, max_w)
                if (ar_size <= 60 or all(
                        hb_text_width(l, ar_size) <= max_w
                        for l in ar_lines)):
                    break
                ar_size -= 4
            ar_imgs = [hb_render_line(l, ar_size, CREAM, stroke=transparent)
                       for l in ar_lines]
            line_h = max(im.height for im in ar_imgs) + int(ar_size * 0.45)
        else:
            while True:
                f_ar = arabic_font(ar_size)
                ar_lines = wrap_arabic(f_ar)
                if (ar_size <= 60 or all(
                        d.textlength(shape_arabic(l), font=f_ar, **RTL)
                        <= max_w for l in ar_lines)):
                    break
                ar_size -= 4
            ar_imgs = None
            line_h = int(ar_size * 1.85)
        en_lines = wrap(d, english, f_en, max_w)
        en_lh = 74
        head_h, gap1, gap2 = 62, 44, 58
        block_h = (head_h + gap1 + 2 + gap2
                   + len(ar_lines) * line_h + gap2
                   + len(en_lines) * en_lh)
        region_top, region_bot = 170, H - 230
        y = region_top + max(0, (region_bot - region_top - block_h) // 2)
        d.text((cx, y), header, font=f_head, fill=GOLD, anchor="ma", **stroke)
        y += head_h + gap1
        d.line([(cx - 140, y), (cx + 140, y)], fill=GOLD, width=2)
        y += 2 + gap2
        if HAS_HB:
            for im in ar_imgs:
                paste_line(img, im, cx, y + (line_h - im.height) // 2)
                y += line_h
        else:
            for line in ar_lines:
                d.text((cx, y + line_h // 2), shape_arabic(line), font=f_ar,
                       fill=CREAM, anchor="mm", **RTL, **stroke)
                y += line_h
        y += gap2
        for line in en_lines:
            d.text((cx, y), line, font=f_en, fill=GREY, anchor="ma", **stroke)
            y += en_lh
        d.text((cx, H - 190), footer, font=f_foot, fill=DIM, anchor="ma",
               **stroke)
        return img

    # Horizontal (16:9) layout.
    f_head = latin_font(34)
    f_en = latin_font(38)
    f_foot = latin_font(28)

    y = 110
    d.text((cx, y), header, font=f_head, fill=GOLD, anchor="ma", **stroke)
    y += 90
    d.line([(cx - 120, y), (cx + 120, y)], fill=GOLD, width=2)
    y += 70

    # Arabic block (centred, wrapped).
    if HAS_HB:
        ar_lines = wrap_arabic_hb(arabic, 76, max_w)
        ar_imgs = [hb_render_line(l, 76, CREAM, stroke=transparent)
                   for l in ar_lines]
        line_h = max(im.height for im in ar_imgs) + int(76 * 0.45)
        for im in ar_imgs:
            paste_line(img, im, cx, y + (line_h - im.height) // 2)
            y += line_h
    else:
        f_ar = arabic_font(76)
        # With libraqm the logical-order text is shaped at draw time
        # (direction="rtl"); without it each line is pre-shaped to
        # visual order by shape_arabic().
        ar_lines = wrap_arabic(f_ar)
        line_h = int(76 * 1.9)
        for line in ar_lines:
            d.text((cx, y + line_h // 2), shape_arabic(line), font=f_ar,
                   fill=CREAM, anchor="mm", **RTL, **stroke)
            y += line_h
    y += 40

    # Translation
    for line in wrap(d, english, f_en, max_w):
        d.text((cx, y), line, font=f_en, fill=GREY, anchor="ma", **stroke)
        y += 58

    d.text((cx, H - 110), footer,
           font=f_foot, fill=DIM, anchor="ma", **stroke)
    return img


def title_frame(W, H, ch, reciter_name, translation_name, channel,
                vertical=False, transparent=False):
    img = Image.new("RGBA" if transparent else "RGB",
                    (W, H), (0, 0, 0, 0) if transparent else BG)
    d = ImageDraw.Draw(img)
    stroke = {"stroke_width": 2, "stroke_fill": (0, 0, 0)} if transparent else {}
    m = 28 if not vertical else 22
    d.rectangle([m, m, W - m, H - m], outline=GOLD, width=2)
    cx, cy = W // 2, H // 2
    f_ar = arabic_font(110 if not vertical else 120)
    f_big = latin_font(54 if not vertical else 60)
    f_med = latin_font(36 if not vertical else 42)
    f_sm = latin_font(28 if not vertical else 34)

    y = cy - (220 if not vertical else 320)
    name_size = 110 if not vertical else 120
    if HAS_HB:
        name_img = hb_render_line(ch["name_arabic"], name_size, CREAM,
                                  stroke=transparent)
        paste_line(img, name_img, cx, y)
        y = y + name_img.height + (60 if not vertical else 70)
    else:
        d.text((cx, y), shape_arabic(ch["name_arabic"]), font=f_ar,
               fill=CREAM, anchor="ma", **RTL, **stroke)
        # measure the tall calligraphic glyphs so nothing overlaps
        bbox = d.textbbox((cx, y), shape_arabic(ch["name_arabic"]), font=f_ar,
                          anchor="ma", **RTL)
        y = bbox[3] + (60 if not vertical else 70)
    d.text((cx, y), f"SURAH {ch['name_simple'].upper()} ({ch['id']})",
           font=f_big, fill=GOLD, anchor="ma", **stroke)
    y += 90 if not vertical else 100
    d.text((cx, y), "Recitation with English Translation",
           font=f_med, fill=GREY, anchor="ma", **stroke)
    y += 70 if not vertical else 80
    rec_line = f"Recited by {reciter_name}  •  {translation_name}"
    if vertical:
        for line in wrap(d, rec_line, f_sm, W - 140):
            d.text((cx, y), line, font=f_sm, fill=DIM, anchor="ma", **stroke)
            y += 46
        y += 24  # breathing room before the channel line
    else:
        d.text((cx, y), rec_line, font=f_sm, fill=DIM, anchor="ma", **stroke)
        y += 60
    d.text((cx, y), channel, font=f_sm, fill=DIM, anchor="ma", **stroke)
    return img


def end_frame(W, H, channel, vertical=False, transparent=False):
    img = Image.new("RGBA" if transparent else "RGB",
                    (W, H), (0, 0, 0, 0) if transparent else BG)
    d = ImageDraw.Draw(img)
    stroke = {"stroke_width": 2, "stroke_fill": (0, 0, 0)} if transparent else {}
    m = 28 if not vertical else 22
    d.rectangle([m, m, W - m, H - m], outline=GOLD, width=2)
    cx, cy = W // 2, H // 2
    d.text((cx, cy - 60), channel, font=latin_font(54 if not vertical else 60),
           fill=GOLD, anchor="ma", **stroke)
    d.text((cx, cy + 30), "Subscribe for daily Quran recitation & tafsir",
           font=latin_font(34 if not vertical else 40), fill=GREY,
           anchor="ma", **stroke)
    return img


# ----------------------------------------------------------------------------
# Backgrounds
# ----------------------------------------------------------------------------

VIDEO_EXTS = (".mp4", ".mov", ".webm", ".mkv")


def make_bg_clip(path, W, H, total):
    """Full-duration background clip: image (static) or video (looped),
    cover-cropped to W x H."""
    from moviepy import ImageClip, VideoFileClip, concatenate_videoclips
    import math
    import numpy as np
    from PIL import Image as PILImage

    ext = os.path.splitext(path)[1].lower()
    if ext in VIDEO_EXTS:
        v = VideoFileClip(path)
        n = max(1, math.ceil(total / v.duration))
        bg = concatenate_videoclips([v] * n).with_duration(total)
        vw, vh = bg.size
        bg = bg.resized(max(W / vw, H / vh))
        w2, h2 = bg.size
        bg = bg.cropped(x_center=w2 / 2, y_center=h2 / 2, width=W, height=H)
    else:
        # Cover-crop once with PIL: far cheaper and leaner than a per-frame
        # moviepy resized/cropped transform during the encode loop.
        img = PILImage.open(path).convert("RGB")
        scale = max(W / img.width, H / img.height)
        img = img.resize((max(1, int(img.width * scale + 0.5)),
                          max(1, int(img.height * scale + 0.5))),
                         PILImage.LANCZOS)
        x = (img.width - W) // 2
        y = (img.height - H) // 2
        img = img.crop((x, y, x + W, y + H))
        bg = ImageClip(np.array(img)).with_duration(total)
    return bg.with_duration(total)


def resolve_background(arg):
    if arg is None:
        return DEFAULT_BG if os.path.exists(DEFAULT_BG) else None
    if arg.lower() == "none":
        return None
    if not os.path.exists(arg):
        sys.exit(f"Background not found: {arg}")
    return arg


# ----------------------------------------------------------------------------
# Build
# ----------------------------------------------------------------------------

def build(args):
    from moviepy import (AudioClip, AudioFileClip, ColorClip, ImageClip,
                         CompositeVideoClip, concatenate_audioclips)
    import numpy as np

    W, H = (1080, 1920) if args.vertical else (1920, 1080)
    reciter_name = RECITERS.get(args.reciter,
                                args.reciter.replace("_", " "))
    translation_name = TRANSLATIONS.get(args.translation,
                                        f"Translation {args.translation}")
    bg_path = resolve_background(getattr(args, "background", None))
    use_bg = bg_path is not None
    if use_bg:
        print(f"Background: {bg_path}")

    print(f"Fetching surah {args.surah} ...")
    ch, items = fetch_surah(args.surah, args.reciter, args.translation)

    if args.verses:
        lo, hi = args.verses
        items = [it for it in items
                 if it["n"] == 0 or (lo <= it["n"] <= hi)]
        if not any(it["n"] != 0 for it in items):
            sys.exit("No verses in that range.")

    header = f"SURAH {ch['name_simple'].upper()} ({ch['id']})"

    # -- segments: (PIL card, audio path or None, fixed duration or None) --
    segments = []
    print("Rendering title card ...")
    segments.append((title_frame(W, H, ch, reciter_name, translation_name,
                                 args.channel, args.vertical, use_bg),
                     None, 3.5))

    total = len([i for i in items if i["n"] != 0])
    for it in items:
        label = ("Bismillah" if it["n"] == 0
                 else f"Verse {it['n']} of {total}")
        footer = (f"{label}  •  Recited by {reciter_name}"
                  if not args.vertical else label)
        print(f"Rendering {it['key']} ...")
        frame = draw_frame(W, H, header, it["arabic"], it["english"],
                           footer, args.vertical, use_bg)
        segments.append((frame, it["audio"], None))

    print("Rendering end card ...")
    segments.append((end_frame(W, H, args.channel, args.vertical, use_bg),
                     None, 3.0))

    # -- audio track + per-segment durations --
    audio_parts, durations = [], []
    for _pil, audio_path, fixed in segments:
        if audio_path:
            a = AudioFileClip(audio_path)
            # pad 0.8s of silence so each verse breathes before the next
            sil = AudioClip(
                lambda t: np.zeros((a.nchannels,)),
                duration=0.8).with_fps(a.fps)
            padded = concatenate_audioclips([a, sil])
            durations.append(padded.duration)
            audio_parts.append(padded)
        else:
            durations.append(fixed)
            audio_parts.append(
                AudioClip(lambda t: np.zeros((2,)),
                          duration=fixed).with_fps(44100))
    full_audio = concatenate_audioclips(audio_parts)
    total_dur = full_audio.duration

    # -- video layers --
    layers = []
    if use_bg:
        layers.append(make_bg_clip(bg_path, W, H, total_dur))
        # cinematic dim so text stays readable over any backdrop
        layers.append(ColorClip((W, H), color=(0, 0, 0))
                      .with_duration(total_dur).with_opacity(0.45))

    def overlay(pil_img, dur):
        arr = np.array(pil_img)
        if use_bg:
            # float32 mask halves the memory vs the float64 default
            mask = (arr[..., 3].astype("float32") / 255.0)
            clip = ImageClip(arr[..., :3]).with_duration(dur).with_mask(
                ImageClip(mask, is_mask=True).with_duration(dur))
        else:
            clip = ImageClip(arr[..., :3]).with_duration(dur)
        return clip.with_position("center")

    print("Compositing ...")
    t = 0.0
    for (pil_img, _a, _f), dur in zip(segments, durations):
        layers.append(overlay(pil_img, dur).with_start(t))
        t += dur

    # The clips hold their own numpy copies now; release the PIL cards.
    del segments
    import gc
    gc.collect()

    final = CompositeVideoClip(layers, size=(W, H)).with_audio(full_audio)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    print(f"Writing {args.out} ...")
    final.write_videofile(args.out, fps=30, codec="libx264",
                          audio_codec="aac",
                          preset=getattr(args, "preset", "medium"),
                          ffmpeg_params=["-movflags", "+faststart"])
    print("Done.")


def parse_verses(s):
    if "-" in s:
        a, b = s.split("-", 1)
        return (int(a), int(b))
    return (int(s), int(s))


def main():
    ap = argparse.ArgumentParser(
        description="Generate a Quran recitation + translation video.")
    ap.add_argument("--surah", type=int, required=True,
                    help="Surah number, e.g. 112")
    ap.add_argument("--reciter", default="Alafasy_128kbps",
                    choices=sorted(RECITERS),
                    help="Voice (default: Alafasy_128kbps)")
    ap.add_argument("--translation", type=int, default=20,
                    help="quran.com translation id (default 20 = Saheeh "
                         "International; 158 = Dr. Israr Ahmad)")
    ap.add_argument("--verses", default=None,
                    help="Limit to verse or range, e.g. '2' or '1-3' "
                         "(handy for Shorts)")
    ap.add_argument("--vertical", action="store_true",
                    help="Render 1080x1920 for YouTube Shorts")
    ap.add_argument("--channel", default="Quran Explained Simply",
                    help="Channel name for title/end cards")
    ap.add_argument("--background", default=None,
                    help="Background image/video path (jpg/png/mp4). "
                         "Default: bundled geometric wallpaper. "
                         "Use 'none' for the plain gradient.")
    ap.add_argument("--preset", default="medium",
                    help="x264 encoding preset (default: medium; use "
                         "'veryfast' for very long videos like a full "
                         "surah)")
    ap.add_argument("--out", default=None, help="Output MP4 path")
    args = ap.parse_args()
    if args.verses:
        args.verses = parse_verses(args.verses)
    if not args.out:
        tag = "short" if args.vertical else "full"
        args.out = os.path.join(
            BASE_DIR, "output",
            f"surah-{args.surah:03d}-{tag}.mp4")
    build(args)


if __name__ == "__main__":
    main()
