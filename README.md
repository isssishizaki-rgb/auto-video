# auto-video

テーマを1つ渡すと、工場が舞台の二人掛け合い解説動画（`output.mp4`）を自動生成します。

```bash
pip install -r requirements.txt
export GEMINI_API_KEY=...        # または .env に GEMINI_API_KEY=... と書く
python make_video.py "工場の安全対策"
```

- 台本・図解イラスト・背景・ナレーションはすべて Gemini API で生成
- 使用モデルは `make_video.py` の候補リストからAPIで使えるものを自動選択（`TEXT_MODEL` / `IMAGE_MODEL` / `TTS_MODEL` 環境変数で上書き可）
- `factory.jpg` がなければ初回に Gemini で生成
- `senpai.png` / `kouhai.png`（透過PNG）を置くと立ち絵が表示され、喋っている方が声に合わせて跳ねる
- 台本と音声は `work/` に保存

## Windows で動かす

1. コマンドプロンプトで `setx GEMINI_API_KEY "あなたのキー"` を実行し、ウィンドウを開き直す
2. このフォルダの `run.bat` をダブルクリックし、テーマを入力する

## 縦型1分リール（make_reel.py）

```bash
python make_reel.py reels/tap3.json   # → reels/tap3.mp4（1080x1920）
```

- 台本は JSON（`reels/tap3.json` が例）。`text` が字幕、`say` があれば読み上げはそちらを使う（読み間違い対策）
- `diagram` にコードで描く図の名前（`make_reel.py` の `dg_*`）を指定すると、動き付きの図解を表示
- 音声は `GEMINI_API_KEY` があれば Gemini TTS、なければ OpenJTalk で合成
