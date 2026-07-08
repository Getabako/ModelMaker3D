# parts.json の bbox に従って参照画像を部品ごとに切り出す。
# 各部品の「実物の見た目」を切り出して、後段の形状生成/テクスチャの素材にする。
# conda env: triposr311 (PIL) で実行。
import sys
import os
import json
from PIL import Image

if len(sys.argv) < 4:
    print("usage: crop_parts.py <parts.json> <reference_image> <out_parts_dir> [pad=0.04]", file=sys.stderr)
    sys.exit(2)

parts_json, ref_path, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
pad = float(sys.argv[4]) if len(sys.argv) > 4 else 0.04

spec = json.load(open(parts_json))
img = Image.open(ref_path).convert("RGBA")
W, H = img.size
os.makedirs(out_dir, exist_ok=True)

for p in spec["parts"]:
    name = p["name"]
    cx, cy, w, h = p["cx"], p["cy"], p["w"], p["h"]
    # bbox(正規化) → ピクセル。padを足す。
    x0 = max(0, int((cx - w / 2 - pad) * W))
    y0 = max(0, int((cy - h / 2 - pad) * H))
    x1 = min(W, int((cx + w / 2 + pad) * W))
    y1 = min(H, int((cy + h / 2 + pad) * H))
    if x1 <= x0 or y1 <= y0:
        print(f"[crop] skip {name}: 不正なbbox", file=sys.stderr)
        continue
    pdir = os.path.join(out_dir, name)
    os.makedirs(pdir, exist_ok=True)
    crop = img.crop((x0, y0, x1, y1))
    # 正方キャンバスに中央配置(背景はグレー)。形状生成が安定する。
    side = max(crop.size)
    canvas = Image.new("RGBA", (side, side), (128, 128, 128, 255))
    canvas.paste(crop, ((side - crop.size[0]) // 2, (side - crop.size[1]) // 2), crop)
    out = os.path.join(pdir, "front.png")
    canvas.convert("RGB").save(out)
    print(f"[crop] {name}: {out} ({crop.size[0]}x{crop.size[1]})")

print("[crop] 完了")
