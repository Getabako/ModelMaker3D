# テクスチャアトラスの「補修」: 暗い面に乗った明るい白点(投影/補完の失敗跡)だけを
# 局所メディアンで消す。本来明るい面(顔/足)は周囲も明るいので保持される。
# さらに既存メッシュ(UV保持)に貼り直して書き出す。有料APIなし。
#
# 使い方: python atlas_repair.py --mesh model_mv.glb --out model_uv.glb --atlas atlas_repair.png
#         [--bright 70] [--darkmax 150] [--size 5] [--iters 2]
import argparse, os, sys
import numpy as np
import trimesh
from PIL import Image, ImageFilter


def despeckle(arr, bright=70, darkmax=150, size=5, iters=2):
    a = arr.astype(np.float32)
    for _ in range(iters):
        img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
        med = np.asarray(img.filter(ImageFilter.MedianFilter(size=size))).astype(np.float32)
        lum = a.mean(2); mlum = med.mean(2)
        # 局所メディアンが暗い(=暗い面)のに自分だけ明るい→白点とみなし置換
        bad = ((lum - mlum) > bright) & (mlum < darkmax)
        a[bad] = med[bad]
    return np.clip(a, 0, 255).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mesh", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--atlas", required=True)
    ap.add_argument("--bright", type=float, default=70)
    ap.add_argument("--darkmax", type=float, default=150)
    ap.add_argument("--size", type=int, default=5)
    ap.add_argument("--iters", type=int, default=2)
    args = ap.parse_args()

    mesh = trimesh.load(args.mesh, force="mesh", process=False)
    try:
        tex = mesh.visual.material.baseColorTexture
    except Exception:
        tex = getattr(mesh.visual, "image", None)
    if tex is None:
        print("ERROR: テクスチャが取れません", file=sys.stderr); sys.exit(2)
    arr = np.asarray(tex.convert("RGB"))
    rep = despeckle(arr, args.bright, args.darkmax, args.size, args.iters)
    img = Image.fromarray(rep, "RGB")

    from trimesh.visual.material import PBRMaterial
    from trimesh.visual import TextureVisuals
    uv = mesh.visual.uv
    mat = PBRMaterial(baseColorTexture=img, metallicFactor=0.0, roughnessFactor=0.9)
    mesh.visual = TextureVisuals(uv=uv, material=mat, image=img)
    os.makedirs(os.path.dirname(os.path.abspath(args.atlas)), exist_ok=True)
    img.save(args.atlas)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    mesh.export(args.out)
    n = int((((arr.astype(np.float32) - rep.astype(np.float32)) ** 2).sum(2) > 1).sum())
    print(f"[atlas_repair] OK -> {args.out} (修正画素 {n})")


if __name__ == "__main__":
    main()
