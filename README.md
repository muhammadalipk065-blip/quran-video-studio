# Quran Recitation + Translation Video Generator

Turn any surah into a polished recitation video — Arabic (Uthmani script) on
screen, English translation below, verse-by-verse human recitation audio,
title/end cards with your channel branding. One command per video.

```
python recitation_video.py --surah 112
```

## ☁️ Easiest option: run in Google Colab (no installation)

Open `Quran_Recitation_Generator.ipynb` in Google Colab
(colab.research.google.com → File → Upload notebook), run the cells top to
bottom, pick your surah in the form, and download the finished MP4.

## What it does

1. **Arabic text** (Uthmani) + **English translation** — fetched from the free
   [quran.com API](https://api.quran.com/docs/) (`api.quran.com/api/v4`).
2. **Human recitation audio, per verse** — downloaded from
   [everyayah.com](https://everyayah.com) (`/data/<reciter>/SSSVVV.mp3`).
   Each verse card stays on screen exactly as long as its audio, plus a
   short pause.
3. **Renders MP4** with moviepy + PIL: deep-navy/gold theme, Amiri Quran
   font, Bismillah card, title card, end card with subscribe CTA.

## Setup

```bash
cd quran-recitation-generator
python3 -m venv .venv
./.venv/bin/pip install moviepy arabic_reshaper python-bidi requests pillow
# font is already in assets/fonts/
```

Requires `ffmpeg` on PATH (for MP4 encoding).

## Usage

```bash
# Full surah, 16:9 (long-form YouTube)
./.venv/bin/python recitation_video.py --surah 112

# One verse as a vertical Short (1080x1920)
./.venv/bin/python recitation_video.py --surah 112 --vertical --verses 2

# A verse range, different reciter + translation
./.venv/bin/python recitation_video.py --surah 36 --verses 1-5 \
    --reciter Husary_128kbps --translation 22

# Your channel name on the cards
./.venv/bin/python recitation_video.py --surah 2 --verses 255 \
    --channel "Quran Explained Simply" --out output/ayat-al-kursi.mp4
```

| Flag | Default | Notes |
|---|---|---|
| `--surah` | (required) | Surah number 1–114 |
| `--reciter` | `Alafasy_128kbps` | `Abdul_Basit_Murattal_192kbps`, `Husary_128kbps`, `Minshawy_Murattal_128kbps`, `Saood_ash-Shuraym_128kbps` |
| `--translation` | `20` | quran.com resource id: 20 Saheeh International, 22 Yusuf Ali, 19 Pickthall (public domain), 85 Abdul Haleem, 203 Hilali & Khan, **158 Dr. Israr Ahmad (Bayan-ul-Quran)** |
| `--verses` | all | e.g. `2` or `1-3` — perfect for Shorts |
| `--vertical` | off | 1080×1920 for YouTube Shorts |
| `--background` | `assets/backgrounds/bg-geometric.jpg` | Image (jpg/png) or video (mp4) backdrop; use `none` for the plain gradient |
| `--channel` | `Quran Explained Simply` | Shown on title/end cards |
| `--out` | `output/surah-NNN-full|short.mp4` | Output path |

Audio downloads are cached in `assets/sNNN_<reciter>/`, so re-renders are fast.

## Backgrounds

Four AI-generated backdrops ship in `assets/backgrounds/` (made for this
project — free for your channel):

- `bg-geometric.jpg` — emerald + gold Islamic pattern (default)
- `bg-mosque-dusk.jpg` — mosque silhouette under a crescent moon
- `bg-golden-particles.jpg` — dark silk with drifting golden light
- `bg-loop-particles.mp4` — animated particle loop (video backdrop)

Use your own image or video instead — videos loop automatically to fill the
runtime. The verse text gets a cinematic dim + subtle stroke so it stays
readable over any backdrop.

```bash
./.venv/bin/python recitation_video.py --surah 112 \
    --background assets/backgrounds/bg-mosque-dusk.jpg

./.venv/bin/python recitation_video.py --surah 112 --verses 2 --vertical \
    --background assets/backgrounds/bg-loop-particles.mp4
```

## Suggested workflow for the channel

- **Juz Amma series**: `--surah 78` … `--surah 114`, one command each.
  Numbered, bingeable, and each doubles as long watch-time content.
- **Shorts**: pick the most powerful verse per surah —
  `--vertical --verses N` — and link each Short to its full video.
- **Memorization loops**: render `--verses 1-3`, then `4-6`, etc.
- **Ayat al-Kursi / last 10 surahs**: standalone high-search-volume videos.

## Licensing — read this before uploading

- **Translations** belong to their translators/publishers. Pickthall (19) is
  public domain; for others (including Saheeh International, 20) check the
  publisher's reuse terms for commercial YouTube use.
- **Recitation audio** comes from everyayah.com's library of established
  qurra. The reciter is credited on screen automatically; respect
  everyayah.com's terms of use.
- **Dr. Israr Ahmad's Bayan-ul-Quran translation (158)** matches this
  channel's niche — verify you have the rights to use it commercially.

## Files

- `recitation_video.py` — the generator
- `assets/fonts/AmiriQuran-Regular.ttf` — Quranic Arabic font (OFL)
- `assets/backgrounds/` — bundled backdrops (jpg + mp4)
- `assets/sNNN_<reciter>/` — cached per-verse MP3s
- `output/` — rendered videos
