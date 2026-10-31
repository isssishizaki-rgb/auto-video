"""台本JSONから縦型1分リール動画 (1080x1920) を作る。

使い方: python make_reel.py reels/tap3.json  →  reels/tap3.mp4
音声: GEMINI_API_KEY があれば Gemini TTS、なければ OpenJTalk（pyopenjtalk-plus）で合成する。
図解: 台本の "diagram" に DIAGRAMS の名前を書くとコードで描いた図（動き付き）を表示する。
"""
import json, math, os, sys, wave
import numpy as np

_CWD = os.getcwd()  # make_video を import すると作業フォルダが移るので先に覚えておく
from PIL import Image, ImageDraw
from moviepy import VideoClip, AudioFileClip, concatenate_videoclips

import make_video as mv
from make_video import CHARS, font, fit_text

W, H, FPS = 1080, 1920, 30
CARD = (50, 270, 1030, 1190)          # 白枠スライド
DIAG = (90, 430, 990, 1150)           # 図解エリア（白枠の中）
DW, DH = DIAG[2] - DIAG[0], DIAG[3] - DIAG[1]
GAP = 0.15                            # セリフ間の無音（秒）

INK, GRAY, METAL = "#1b1f24", "#9aa4ae", "#c9d1d9"
CHIP, BLUE, PINK, GREEN = "#ff8a00", "#2b6cff", "#ff4f7a", "#14a05a"

# OpenJTalk 用の声の作り分け（mei の声を高さと速さで変える）
JTALK = {"A": {"half_tone": -3.5, "speed": 1.15}, "B": {"half_tone": 1.5, "speed": 1.2}}


# ---------------- 音声 ----------------

def voice_level(pcm16, rate):
    s = np.abs(pcm16.astype(np.float32))
    step = rate // FPS
    vol = np.array([s[i:i + step].mean() for i in range(0, len(s), step)] or [0])
    return np.clip(vol / (vol.max() or 1) * 1.8, 0, 1)


def make_voice(line, path):
    sp = line["speaker"]
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return mv.make_voice(line["text"], CHARS[sp]["voice"], path)
    import pyopenjtalk
    x, sr = pyopenjtalk.tts(line.get("say", line["text"]), **JTALK[sp])
    pcm = np.clip(x, -32768, 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes())
    return voice_level(pcm, sr)


# ---------------- 図解 ----------------

def ctext(d, xy, text, size, fill=INK, anchor="mm", **kw):
    d.text(xy, text, font=font(size), fill=fill, anchor=anchor, **kw)


def arrow(d, x0, y0, x1, y1, color, width=12, head=34):
    d.line((x0, y0, x1, y1), fill=color, width=width)
    a = math.atan2(y1 - y0, x1 - x0)
    pts = [(x1, y1)] + [(x1 - head * math.cos(a + s), y1 - head * math.sin(a + s)) for s in (0.45, -0.45)]
    d.polygon(pts, fill=color)


def hatch_block(d, box):
    d.rectangle(box, fill="#e6e9ed", outline=GRAY, width=4)
    x0, y0, x1, y1 = box
    for k in range(int(x0) - int(y1 - y0), int(x1), 28):
        a, b = max(k, x0), min(k + (y1 - y0), x1)
        d.line((a, y1 - (a - k), b, y1 - (b - k)), fill="#d0d5db", width=2)


def draw_tap(d, cx, top, bottom, kind, w=80):
    """縦向きのタップ。kind: point / spiral / roll"""
    shank_end = top + (bottom - top) * 0.45
    d.rectangle((cx - w * 0.38, top, cx + w * 0.38, shank_end), fill="#8d99a6")
    d.rectangle((cx - w / 2, shank_end, cx + w / 2, bottom - 30), fill=METAL, outline="#6b7783", width=3)
    d.polygon([(cx - w / 2, bottom - 30), (cx + w / 2, bottom - 30), (cx + w * 0.25, bottom), (cx - w * 0.25, bottom)],
              fill=METAL, outline="#6b7783")
    y = shank_end + 10
    while y < bottom - 34:
        if kind == "roll":
            d.arc((cx - w / 2 - 6, y - 8, cx + w / 2 + 6, y + 8), 0, 180, fill="#6b7783", width=4)
        elif kind == "spiral":
            d.line((cx - w / 2, y + 16, cx + w / 2, y - 10), fill="#6b7783", width=4)
        else:
            d.line((cx - w / 2, y + 6, cx + w / 2, y - 6), fill="#6b7783", width=4)
        y += 22
    if kind == "spiral":  # ねじれ溝
        for off in (-14, 14):
            d.line((cx + off - 18, bottom - 40, cx + off + 18, shank_end + 6), fill="#4a5560", width=5)
    if kind == "point":   # 先端の斜めの刃（ポイント）
        d.line((cx - w / 2, bottom - 90, cx, bottom - 30), fill="#4a5560", width=5)


def chips(d, path_fn, t, n=7, speed=0.45, r=13):
    for i in range(n):
        u = (t * speed + i / n) % 1.0
        x, y = path_fn(u)
        rr = r * (0.7 + 0.3 * math.sin(i * 2.1))
        d.polygon([(x - rr, y), (x - rr * 0.2, y - rr), (x + rr, y - rr * 0.3), (x + rr * 0.3, y + rr)], fill=CHIP)


def dg_tap_types(d, t, p):
    items = [("point", "ポイント", "切りくず↓奥へ", BLUE),
             ("spiral", "スパイラル", "切りくず↑手前へ", PINK),
             ("roll", "ロール", "切りくずなし", GREEN)]
    for i, (kind, name, sub, col) in enumerate(items):
        cx = 150 + i * 300
        bob = 8 * math.sin(t * 3 + i)
        draw_tap(d, cx, 40 + bob, 470 + bob, kind, w=90)
        ctext(d, (cx, 545), name, 52, fill=col)
        ctext(d, (cx, 615), sub, 34, fill=INK)


def dg_tap_point(d, t, p):
    hatch_block(d, (120, 170, 380, 480)); hatch_block(d, (520, 170, 780, 480))
    ctext(d, (250, 530), "貫通穴", 40, fill=INK)
    ctext(d, (250, 580), "（突き抜けた穴）", 30, fill=GRAY)
    dip = 30 * min(1, t / 2)
    draw_tap(d, 450, 0 + dip, 420 + dip, "point", w=110)
    chips(d, lambda u: (450 + 30 * math.sin(u * 9), 470 + u * 230), t, speed=0.6)
    arrow(d, 640, 560, 640, 690, CHIP)
    ctext(d, (790, 625), "穴の奥へ", 48, fill=CHIP)


def dg_tap_spiral(d, t, p):
    hatch_block(d, (120, 230, 780, 640))
    d.rectangle((385, 230, 515, 520), fill="white", outline=GRAY, width=4)
    ctext(d, (450, 600), "止まり穴（底がある穴）", 34, fill=INK)
    draw_tap(d, 450, 20, 500, "spiral", w=110)
    chips(d, lambda u: (450 + 75 * math.sin(u * 14), 500 - u * 470), t, speed=0.55)
    arrow(d, 680, 200, 680, 50, CHIP)
    ctext(d, (790, 125), "手前へ", 48, fill=CHIP)


def dg_tap_roll(d, t, p):
    hatch_block(d, (120, 120, 780, 520))
    d.rectangle((380, 120, 520, 520), fill="white")
    # 押し広げられてできたねじ山（波形の壁）
    for side in (-1, 1):
        x = 450 + side * 70
        pts = [(x + side * 14 * math.sin(k * 0.5), 120 + k * 10) for k in range(41)]
        d.line(pts, fill=INK, width=5)
    draw_tap(d, 450, 0, 500, "roll", w=110)
    pulse = 0.5 + 0.5 * math.sin(t * 5)
    for y in (250, 340, 430):
        for side in (-1, 1):
            arrow(d, 450 + side * 70, y, 450 + side * (110 + 25 * pulse), y, GREEN, width=8, head=22)
    ctext(d, (450, 590), "押し広げてねじ山を作る → 切りくず0", 38, fill=GREEN)
    ctext(d, (450, 660), "※下穴径は切削タップと別。専用表で確認", 30, fill=INK)


def dg_tap_feed(d, t, p):
    rows = [(0.0, "回転数 = 1000×加工速度 ÷ (π×呼び径)", 40, INK),
            (0.0, "例) M6×1・加工速度10m/min", 44, BLUE),
            (0.25, "1000×10 ÷ (3.14×6) ≈ 530回転/分", 46, INK),
            (0.55, "送り = 回転数 × ピッチ", 46, INK),
            (0.62, "530 × 1mm = 530mm/分", 60, PINK)]
    y = 40
    for start, text, size, col in rows:
        if p >= start:
            ctext(d, (450, y), text, size, fill=col)
        y += 115
    ctext(d, (450, 660), "※10m/minは計算用の仮定。実際はメーカー条件表で", 28, fill=GRAY)


def dg_tap_summary(d, t, p):
    rows = [("貫通穴", "ポイント", BLUE), ("止まり穴", "スパイラル", PINK), ("切りくずを避けたい", "ロール", GREEN)]
    for i, (a, b, col) in enumerate(rows):
        if p < i * 0.18:
            continue
        y = 40 + i * 200
        d.rounded_rectangle((20, y, 880, y + 160), 24, fill="#f3f5f8", outline=col, width=6)
        ctext(d, (40, y + 80), a, 44, anchor="lm")
        arrow(d, 470, y + 80, 560, y + 80, col, width=10, head=26)
        ctext(d, (860, y + 80), b, 56, fill=col, anchor="rm")
    if p > 0.5:
        ctext(d, (450, 660), "穴の形と材料で選ぶ！", 44, fill=INK)


DIAGRAMS = {k[3:]: v for k, v in globals().items() if k.startswith("dg_")}


# ---------------- 画面 ----------------

def make_background(title):
    top, bot = np.array([24, 34, 46]), np.array([46, 62, 78])
    g = np.linspace(0, 1, H)[:, None, None]
    bg = Image.fromarray((top * (1 - g) + bot * g).repeat(W, axis=1).astype(np.uint8))
    d = ImageDraw.Draw(bg)
    for k in range(-H, W, 60):
        d.line((k, H, k + H, 0), fill="#2a3846", width=2)
    for x in range(0, W, 60):  # 黄黒の注意帯
        d.polygon([(x, 230), (x + 30, 230), (x + 10, 250), (x - 20, 250)], fill="#f5c400")
    ctext(d, (W / 2, 140), title, 84, fill="white", stroke_width=6, stroke_fill="#000")
    return bg


def make_scene_base(bg, scene):
    img = bg.copy()
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(CARD, 36, fill="white", outline="#f5c400", width=12)
    f, lines, size = fit_text(d, scene["heading"], 68, CARD[2] - CARD[0] - 80, 1)
    d.text((W / 2, 350), lines[0], font=f, fill=INK, anchor="mm")
    d.line((120, 405, W - 120, 405), fill="#f5c400", width=6)
    return img


def make_caption(line):
    sp = line["speaker"]
    cap = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(cap)
    d.rounded_rectangle((40, 1250, W - 40, 1590), 30, fill=(0, 0, 0, 150))
    tag = CHARS[sp]["name"]
    tx = 70 if sp == "A" else W - 70
    d.rounded_rectangle((tx - 10 if sp == "A" else tx - 190, 1215, tx + 190 if sp == "A" else tx + 10, 1285),
                        20, fill=CHARS[sp]["color"])
    ctext(d, (tx + 90 if sp == "A" else tx - 90, 1250), tag, 40, fill="white")
    f, lines, size = fit_text(d, line["text"].rstrip("。"), 66, W - 140, 3)
    y = 1420 - (len(lines) - 1) * size * 0.65
    for t in lines:
        d.text((W / 2, y), t, font=f, fill="white", anchor="mm", stroke_width=7, stroke_fill=CHARS[sp]["color"])
        y += size * 1.3
    return cap


def load_sprites():
    sp = {}
    for k, c in CHARS.items():
        if os.path.exists(c["image"]):
            im = Image.open(c["image"]).convert("RGBA")
            sp[k] = im.resize((int(im.width * 460 / im.height), 460))
    return sp


def main(script_path):
    script_path = os.path.join(_CWD, script_path)
    script = json.load(open(script_path, encoding="utf-8"))
    out = os.path.splitext(script_path)[0] + ".mp4"
    work = os.path.join(mv.WORK, "reel")
    os.makedirs(work, exist_ok=True)
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        mv.setup()
    else:
        print("GEMINI_API_KEY なし → OpenJTalk で音声を合成します")

    # 先に全セリフの音声を作り、シーンの長さを確定させる
    idx = 0
    for scene in script["scenes"]:
        for line in scene["lines"]:
            line["wav"] = os.path.join(work, f"line{idx}.wav"); idx += 1
            line["level"] = make_voice(line, line["wav"])
            line["audio"] = AudioFileClip(line["wav"])
        scene["duration"] = sum(l["audio"].duration + GAP for l in scene["lines"])
    total = sum(s["duration"] for s in script["scenes"])
    print(f"合計 {total:.1f} 秒")

    bg = make_background(script["title"])
    sprites = load_sprites()
    clips, elapsed = [], 0.0
    for scene in script["scenes"]:
        print("シーン作成中:", scene["heading"])
        base = make_scene_base(bg, scene)
        diagram = DIAGRAMS.get(scene.get("diagram"))
        offset = 0.0
        for line in scene["lines"]:
            clips.append(line_clip(base, diagram, sprites, scene, line, offset, elapsed, total))
            dur = line["audio"].duration + GAP
            offset += dur; elapsed += dur
    concatenate_videoclips(clips).write_videofile(out, fps=FPS, codec="libx264", audio_codec="aac")
    print("完成！", out)


def line_clip(base, diagram, sprites, scene, line, offset, elapsed, total):
    cap = make_caption(line)
    level, sp = line["level"], line["speaker"]

    def frame(t):
        img = base.copy()
        st = offset + t                       # シーン内の経過時間
        if diagram:
            layer = Image.new("RGBA", (DW, DH), (255, 255, 255, 0))
            diagram(ImageDraw.Draw(layer), st, st / scene["duration"])
            img.paste(layer, DIAG[:2], layer)
        for k, im in sprites.items():
            jump = int(level[min(int(t * FPS), len(level) - 1)] * 25) if k == sp else 0
            x = 0 if k == "A" else W - im.width
            img.paste(im, (x, H - im.height - jump), im)
        img.paste(cap, (0, 0), cap)
        d = ImageDraw.Draw(img)            # 上端の進行バー
        d.rectangle((0, 0, int(W * (elapsed + t) / total), 12), fill="#f5c400")
        return np.array(img)

    return VideoClip(frame, duration=line["audio"].duration + GAP).with_audio(line["audio"])


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "reels/tap3.json")
