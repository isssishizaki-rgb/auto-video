"""テーマを1つ渡すと、工場が舞台の二人掛け合い解説動画 (output.mp4) を作る。

使い方: python make_video.py "工場の安全対策"
必要: 環境変数 GEMINI_API_KEY（または同じフォルダの .env に GEMINI_API_KEY=...）
"""
import json, wave, sys, io, os, time
import numpy as np
from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from moviepy import VideoClip, AudioFileClip, concatenate_videoclips

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

# .env があれば読み込む（GEMINI_API_KEY 用）
if os.path.exists(".env"):
    for row in open(".env", encoding="utf-8"):
        k, _, v = row.strip().partition("=")
        if k and v and not k.startswith("#"):
            os.environ.setdefault(k, v.strip().strip('"'))

# 上から順に、APIで使えるものを自動で選ぶ（環境変数で上書き可）
TEXT_MODELS  = ["gemini-3.1-pro-preview", "gemini-3.1-pro", "gemini-2.5-pro"]
IMAGE_MODELS = ["gemini-nano-banana-2.1", "gemini-3.1-flash-image",
                "gemini-3.1-flash-image-preview", "gemini-2.5-flash-image"]
TTS_MODELS   = ["gemini-3.8-flash-tts", "gemini-3.1-flash-tts-preview",
                "gemini-2.5-flash-preview-tts"]
FONT = "NotoSansJP-Black.ttf"
BG = "factory.jpg"
WORK = "work"
W, H, FPS = 1920, 1080, 30

CHARS = {
    "A": {"name": "先輩", "voice": "Charon", "image": "senpai.png",
          "pos": (40, 420), "color": "#2b6cff"},
    "B": {"name": "後輩", "voice": "Kore", "image": "kouhai.png",
          "pos": (1300, 420), "color": "#ff4f7a"},
}

client = None
TEXT_MODEL = IMAGE_MODEL = TTS_MODEL = None


def setup():
    global client, TEXT_MODEL, IMAGE_MODEL, TTS_MODEL
    client = genai.Client()
    try:
        available = {m.name.removeprefix("models/") for m in client.models.list()}
    except Exception as e:
        print("モデル一覧を取得できませんでした:", e)
        available = set()

    def pick(env, candidates):
        if os.environ.get(env):
            return os.environ[env]
        return next((m for m in candidates if m in available), candidates[0])

    TEXT_MODEL = pick("TEXT_MODEL", TEXT_MODELS)
    IMAGE_MODEL = pick("IMAGE_MODEL", IMAGE_MODELS)
    TTS_MODEL = pick("TTS_MODEL", TTS_MODELS)
    print(f"使用モデル: 台本={TEXT_MODEL} 画像={IMAGE_MODEL} 音声={TTS_MODEL}")


def retry(fn, tries=4):
    for n in range(tries):
        try:
            return fn()
        except Exception as e:
            if n == tries - 1:
                raise
            print(f"  再試行 {n + 1}/{tries - 1}: {e}")
            time.sleep(5 * 2 ** n)


def font(size):
    return ImageFont.truetype(FONT, size)


def wrap(d, text, f, max_w):
    """日本語を1文字ずつ詰めて max_w で折り返す"""
    lines, cur = [], ""
    for ch in text:
        if d.textlength(cur + ch, font=f) > max_w and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    return lines + [cur] if cur else lines


def fit_text(d, text, size, max_w, max_lines):
    """max_lines 行に収まるまでフォントを小さくする"""
    while True:
        f = font(size)
        lines = wrap(d, text, f, max_w)
        if len(lines) <= max_lines or size <= 24:
            return f, lines, size
        size -= 4


def make_script(topic):
    prompt = f"""「{topic}」を工場が舞台の掛け合い解説動画にします。
A={CHARS['A']['name']}（解説役）、B={CHARS['B']['name']}（質問役）。
6〜10シーン。JSON配列のみ出力。
各要素: {{"heading": 15字以内の短い大見出し, "image_prompt": 図解イラストの英語プロンプト,
          "lines": [{{"speaker":"A"か"B","text":40字以内のセリフ}}]}}"""

    def call():
        res = client.models.generate_content(model=TEXT_MODEL, contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"))
        data = json.loads(res.text)
        if isinstance(data, dict):  # {"scenes": [...]} のように包まれて返る場合
            data = next(v for v in data.values() if isinstance(v, list))
        return data
    return retry(call)


def generate_image(prompt):
    res = client.models.generate_content(model=IMAGE_MODEL, contents=prompt)
    for part in res.candidates[0].content.parts:
        if part.inline_data:
            return Image.open(io.BytesIO(part.inline_data.data))
    raise RuntimeError("画像が返ってきませんでした")


def make_illust(p):
    try:
        return retry(lambda: generate_image(
            f"Simple flat infographic illustration, white background, no text: {p}"),
            tries=2).convert("RGBA")
    except Exception as e:
        print("  イラスト生成をスキップ:", e)


def ensure_background():
    if os.path.exists(BG):
        return
    try:
        print("背景画像を生成中...")
        im = retry(lambda: generate_image(
            "Photorealistic wide shot of a clean modern factory floor interior, "
            "machines and conveyor lines, bright lighting, no people, no text, 16:9"), tries=2)
        im.convert("RGB").save(BG, quality=92)
    except Exception as e:
        print("背景画像の生成をスキップ（単色背景にします）:", e)


def make_base(scene):
    if os.path.exists(BG):
        bg = Image.open(BG).convert("RGB").resize((W, H)).filter(ImageFilter.GaussianBlur(8))
    else:
        bg = Image.new("RGB", (W, H), "#4a5560")
    d = ImageDraw.Draw(bg)
    d.rounded_rectangle((380, 60, 1540, 820), 30, fill="white", outline="#f5c400", width=10)
    f, lines, size = fit_text(d, scene["heading"], 80, 1060, 1)
    for i, t in enumerate(lines[:2]):
        tw = d.textlength(t, font=f)
        d.text(((W - tw) / 2, 90 + i * size * 1.2), t, font=f, fill="#111")
    il = make_illust(scene["image_prompt"])
    if il:
        il.thumbnail((1000, 580))
        bg.paste(il, ((W - il.width) // 2, 210), il)
    return bg


def load_sprites():
    sp = {}
    for k, c in CHARS.items():
        if os.path.exists(c["image"]):
            im = Image.open(c["image"]).convert("RGBA")
            r = 640 / im.height
            sp[k] = im.resize((int(im.width * r), 640))
    return sp


def make_voice(text, voice, path):
    def call():
        res = client.models.generate_content(model=TTS_MODEL, contents=text,
            config=types.GenerateContentConfig(response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)))))
        for part in res.candidates[0].content.parts:
            if part.inline_data:
                return part.inline_data.data
        raise RuntimeError("音声が返ってきませんでした")
    pcm = retry(call)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
    s = np.abs(np.frombuffer(pcm, dtype=np.int16).astype(np.float32))
    step = 24000 // FPS
    vol = np.array([s[i:i+step].mean() for i in range(0, len(s), step)] or [0])
    return np.clip(vol / (vol.max() or 1) * 1.8, 0, 1)


def line_clip(base, sprites, line, idx):
    sp = line["speaker"] if line["speaker"] in CHARS else "A"
    path = os.path.join(WORK, f"voice{idx}.wav")
    level = make_voice(line["text"], CHARS[sp]["voice"], path)
    audio = AudioFileClip(path)
    # テロップは立ち絵より手前に出すため別レイヤーに描く
    caption = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(caption)
    f, lines, size = fit_text(d, line["text"], 58, 1800, 2)
    y = 1040 - len(lines) * size * 1.25
    for t in lines:
        tw = d.textlength(t, font=f)
        d.text(((W - tw) / 2, y), t, font=f, fill="white",
               stroke_width=8, stroke_fill=CHARS[sp]["color"])
        y += size * 1.25
    still = base.copy()
    still.paste(caption, (0, 0), caption)
    still_arr = np.array(still)

    def frame(t):
        if not sprites:
            return still_arr
        img = base.copy()
        n = min(int(t * FPS), len(level) - 1)
        for k, im in sprites.items():
            x, y = CHARS[k]["pos"]
            jump = int(level[n] * 25) if k == sp else 0
            img.paste(im, (x, y - jump), im)
        img.paste(caption, (0, 0), caption)
        return np.array(img)
    return VideoClip(frame, duration=audio.duration + 0.3).with_audio(audio)


def main(topic):
    setup()
    os.makedirs(WORK, exist_ok=True)
    ensure_background()
    sprites = load_sprites()
    script = make_script(topic)
    with open(os.path.join(WORK, "script.json"), "w", encoding="utf-8") as fp:
        json.dump(script, fp, ensure_ascii=False, indent=2)
    clips, i = [], 0
    for scene in script:
        print("シーン作成中:", scene["heading"])
        base = make_base(scene)
        for line in scene["lines"]:
            clips.append(line_clip(base, sprites, line, i)); i += 1
    concatenate_videoclips(clips).write_videofile(
        "output.mp4", fps=FPS, codec="libx264", audio_codec="aac")
    print("完成！ output.mp4")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "工場の安全対策")
