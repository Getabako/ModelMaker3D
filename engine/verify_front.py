# 正面照合ゲート: 完成モデルの正面レンダが入力の front.png / back.png のどちらに近いかを判定。
# 前後が逆に焼かれていれば back に近くなる → exit 2 (呼び出し側で反転リトライ)。
# usage: python verify_front.py --render snap_front.png --front front.png --back back.png
import argparse
import sys

import numpy as np
from PIL import Image


def fg_crop(path, size=48):
    im = Image.open(path).convert("RGBA")
    a = np.asarray(im).astype(np.float64)
    alpha = a[:, :, 3]
    rgb = a[:, :, :3]
    if alpha.min() > 250:  # 背景が白画像(アルファ無し)
        mask = np.abs(rgb - rgb[0, 0]).sum(axis=2) > 40
    else:
        mask = alpha > 32
    ys, xs = np.where(mask)
    if len(ys) < 50:
        return None, None
    crop = rgb[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    mcrop = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    ci = np.asarray(Image.fromarray(crop.astype(np.uint8)).resize((size, size), Image.LANCZOS), dtype=np.float64)
    mi = np.asarray(Image.fromarray((mcrop * 255).astype(np.uint8)).resize((size, size), Image.NEAREST)) > 127
    return ci, mi


def masked_mse(a, ma, b, mb):
    m = ma & mb
    if m.sum() < 50:
        return 1e9
    d = a[m] - b[m]
    return float((d * d).mean())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", required=True)
    ap.add_argument("--front", required=True)
    ap.add_argument("--back", required=True)
    args = ap.parse_args()

    r, mr = fg_crop(args.render)
    f, mf = fg_crop(args.front)
    b, mb = fg_crop(args.back)
    if r is None or f is None:
        print("[verify_front] SKIP (前景が読めない)")
        return 0
    mse_f = masked_mse(r, mr, f, mf)
    mse_b = masked_mse(r, mr, b, mb) if b is not None else 1e9
    print(f"[verify_front] mse_front={mse_f:.1f} mse_back={mse_b:.1f}")
    if mse_b < mse_f * 0.85:
        print("[verify_front] NG: 正面レンダが back 画像に近い → 前後逆の疑い")
        return 2
    print("[verify_front] OK: 正面が front 画像に一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
