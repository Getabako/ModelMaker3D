# 手描き/編集したテクスチャPNGを、UV付きメッシュに貼り直して書き出す。
# 手描きワークフロー: uv_layout_quad.png を下絵に atlas を塗る → これで再適用。
# 使い方: python apply_atlas.py --mesh chibi_quad_uv.glb --atlas painted.png --out model_painted.glb
import argparse, os, sys
import numpy as np
import trimesh
from PIL import Image


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mesh", required=True)
    ap.add_argument("--atlas", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    mesh = trimesh.load(args.mesh, force="mesh", process=False)
    uv = getattr(mesh.visual, "uv", None)
    if uv is None:
        print("ERROR: メッシュにUVがありません", file=sys.stderr); sys.exit(2)
    img = Image.open(args.atlas).convert("RGB")
    from trimesh.visual.material import PBRMaterial
    from trimesh.visual import TextureVisuals
    mat = PBRMaterial(baseColorTexture=img, metallicFactor=0.0, roughnessFactor=0.9)
    mesh.visual = TextureVisuals(uv=uv, material=mat, image=img)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    mesh.export(args.out)
    print("[apply_atlas] OK ->", args.out)


if __name__ == "__main__":
    main()
