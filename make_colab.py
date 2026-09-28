#!/usr/bin/env python3
"""Builds Quran_Recitation_Generator.ipynb from recitation_video.py."""
import json
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(BASE, "recitation_video.py")) as f:
    src = f.read()

# --- Adapt the script for Colab -------------------------------------------
# 1. Fixed content dir instead of script-relative paths.
src = src.replace(
    'BASE_DIR = os.path.dirname(os.path.abspath(__file__))',
    'BASE_DIR = "/content"')
# 2. Drop the CLI entrypoint (argparse main + __main__ guard); keep
#    parse_verses() which the form cell uses. Everything from
#    "def main():" to end of file goes.
src = re.sub(r"\ndef main\(\):.*$", "", src, flags=re.DOTALL).rstrip() + "\n"


def code(source):
    lines = source.splitlines(keepends=True)
    return {"cell_type": "code", "metadata": {},
            "source": lines, "outputs": [], "execution_count": None}


def md(source):
    return {"cell_type": "markdown", "metadata": {},
            "source": [source]}


cells = [
    md("# 🕌 Quran Recitation + Translation Video Generator\n"
       "\n"
       "Generate a polished recitation video for any surah — Arabic (Uthmani) "
       "on screen, English translation below, verse-by-verse human recitation "
       "audio — right here in your browser. No installation on your computer needed.\n"
       "\n"
       "**How to use:**\n"
       "1. Run the cells below **in order** (▶ button on each, top to bottom).\n"
       "2. In the last cell, pick your surah, voice and format, then run it.\n"
       "3. The finished MP4 downloads automatically when done.\n"
       "\n"
       "_First run takes a few minutes (installs video tools). Later runs are faster._"),

    md("## Step 1 — Install video tools"),
    code("!pip install -q moviepy requests pillow\n"
         "print('tools installed')"),

    md("## Step 2 — Download the Quranic Arabic font"),
    code("import os\n"
         "os.makedirs('/content/assets/fonts', exist_ok=True)\n"
         "!curl -sL -o /content/assets/fonts/AmiriQuran-Regular.ttf "
         "\"https://github.com/google/fonts/raw/main/ofl/amiriquran/AmiriQuran-Regular.ttf\"\n"
         "from PIL import features\n"
         "print('font ready:', os.path.getsize('/content/assets/fonts/AmiriQuran-Regular.ttf'), 'bytes')\n"
         "print('Arabic shaping (raqm):', features.check('raqm'))"),

    md("## Step 3 — Load the generator\n"
       "_This cell defines all the video-building code. Just run it._"),
    code(src),

    md("## Step 3b — Download the bundled backgrounds\n"
       "_Four backdrops made for this project. Run once per session._"),
    code(
        "import os, urllib.request\n"
        "os.makedirs('/content/assets/backgrounds', exist_ok=True)\n"
        "BG_URLS = {\n"
        "    'bg-geometric.jpg': 'https://muse.ai/files/1455867154266273/1408388931497710/i7fonl83xo2fn5o8cum4rgmv/bg-geometric.jpg',\n"
        "    'bg-mosque-dusk.jpg': 'https://muse.ai/files/1455867154266273/1686132946458676/ezdnelq9dfscvhtsrdgfa2qx/bg-mosque-dusk.jpg',\n"
        "    'bg-golden-particles.jpg': 'https://muse.ai/files/1455867154266273/1370224878635207/v8ldvowjn7iybyuxbessrx1w/bg-golden-particles.jpg',\n"
        "    'bg-loop-particles.mp4': 'https://muse.ai/files/1455867154266273/3400029806845170/1dojdfwciyicb7knl0kqpdch/bg-loop-particles.mp4',\n"
        "}\n"
        "for name, url in BG_URLS.items():\n"
        "    dest = f'/content/assets/backgrounds/{name}'\n"
        "    if not os.path.exists(dest):\n"
        "        print('downloading', name)\n"
        "        urllib.request.urlretrieve(url, dest)\n"
        "print('backgrounds ready:', os.listdir('/content/assets/backgrounds'))\n"
    ),

    md("## (Optional) Browse surah numbers\n"
       "_Run this if you need the number for a surah._"),
    code("import requests\n"
         "chapters = requests.get('https://api.quran.com/api/v4/chapters').json()['chapters']\n"
         "for c in chapters:\n"
         "    print(f\"{c['id']:3d}  {c['name_simple']} ({c['verses_count']} verses)\")"),

    md("## Step 4 — Generate your video 🎬\n"
       "_Fill in the form, then run the cell._"),
    code(
        "#@title Generate recitation video\n"
        "surah = 112  #@param {type:\"number\", description: \"Surah number 1-114\"}\n"
        "reciter = \"Alafasy_128kbps\"  #@param [\"Alafasy_128kbps\", \"Abdul_Basit_Murattal_192kbps\", \"Husary_128kbps\", \"Minshawy_Murattal_128kbps\", \"Saood_ash-Shuraym_128kbps\"] {description: \"Reciter voice\"}\n"
        "translation = 20  #@param [20, 158, 22, 19, 85, 203] {description: \"20=Saheeh International, 158=Dr. Israr Ahmad (Bayan-ul-Quran), 22=Yusuf Ali, 19=Pickthall\"}\n"
        "verses = \"\"  #@param {type:\"string\", description: \"Verse or range, e.g. 2 or 1-3 (empty = full surah). Use with Vertical for Shorts.\"}\n"
        "vertical = False  #@param {type:\"boolean\", description: \"ON = 1080x1920 Short, OFF = 16:9 long-form\"}\n"
        "channel = \"Quran Explained Simply\"  #@param {type:\"string\", description: \"Channel name on title/end cards\"}\n"
        "background = \"bg-geometric.jpg\"  #@param [\"bg-geometric.jpg\", \"bg-mosque-dusk.jpg\", \"bg-golden-particles.jpg\", \"bg-loop-particles.mp4\", \"none\"] {description: \"Backdrop (run Step 3b first). Upload your own to /content and type its name for a custom one.\"}\n"
        "\n"
        "class Args: pass\n"
        "args = Args()\n"
        "args.surah = int(surah)\n"
        "args.reciter = reciter\n"
        "args.translation = int(translation)\n"
        "args.verses = parse_verses(verses) if verses.strip() else None\n"
        "args.vertical = bool(vertical)\n"
        "args.channel = channel\n"
        "args.background = None\n"
        "if background != \"none\":\n"
        "    _cands = [f\"/content/assets/backgrounds/{background}\",\n"
        "              f\"/content/{background}\", background]\n"
        "    args.background = next((c for c in _cands if os.path.exists(c)),\n"
        "                           _cands[0])\n"
        "tag = 'short' if args.vertical else 'full'\n"
        "args.out = f\"/content/output/surah-{args.surah:03d}-{tag}.mp4\"\n"
        "\n"
        "build(args)\n"
        "\n"
        "try:\n"
        "    from google.colab import files\n"
        "    files.download(args.out)\n"
        "    print('download started')\n"
        "except ImportError:\n"
        "    print(f\"saved to {args.out} (not in Colab, skipping auto-download)\")\n"
    ),

    md("## Tips\n"
       "\n"
       "- **Juz Amma series:** run Step 4 once per surah (78 → 114).\n"
       "- **Shorts:** set `verses` to one verse (e.g. `2`) and tick `vertical`.\n"
       "- **Memorization loops:** render ranges like `1-3`, then `4-6`.\n"
       "- Files stay in this session's `/content/output/` until the runtime "
       "recycles (re-run Step 4 any time).\n"
       "- ⚖️ Check translation/recitation reuse terms before monetising "
       "(see the README in the project folder)."),
]

nb = {
    "nbformat": 4,
    "nbformat_minor": 0,
    "metadata": {
        "kernelspec": {"display_name": "Python 3",
                       "language": "python", "name": "python3"},
        "accelerator": "GPU",
    },
    "cells": cells,
}

out = os.path.join(BASE, "Quran_Recitation_Generator.ipynb")
with open(out, "w") as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)
print("wrote", out, f"({os.path.getsize(out)//1024} KB)")
