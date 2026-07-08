# 複数視点(正面/横/後ろ/上/下)の実写真をメッシュに投影し、頂点カラーとして焼き込む。
# TripoSR で作った形状(正面由来)に、ユーザーの複数写真の見た目を全方向から貼り付ける。
# 有料APIは使わない。conda env: triposr311 (trimesh, numpy, PIL) で実行。
#
# 使い方:
#   python project_multiview.py --mesh mesh.obj --out model.glb \
#       --view front=/path/front.png --view right=/path/right.png \
#       --view back=/path/back.png  --view left=/path/left.png \
#       [--view top=/path/top.png] [--view bottom=/path/bottom.png] \
#       [--front-axis +z] [--power 2.0]
#
# 各ビューの向き(オブジェクトから見たカメラ方向):
#   front=+Z, back=-Z, right=+X, left=-X, top=+Y, bottom=-Y  (--front-axis で回転補正可)

import argparse
import sys
import numpy as np
import trimesh
from PIL import Image


# ビュー名 -> カメラ方向(オブジェクト中心から見たカメラ位置の単位ベクトル)
BASE_DIRS = {
    "front": np.array([0.0, 0.0, 1.0]),
    "back": np.array([0.0, 0.0, -1.0]),
    "right": np.array([1.0, 0.0, 0.0]),
    "left": np.array([-1.0, 0.0, 0.0]),
    "top": np.array([0.0, 1.0, 0.0]),
    "bottom": np.array([0.0, -1.0, 0.0]),
}


def rot_y(deg):
    r = np.radians(deg)
    c, s = np.cos(r), np.sin(r)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def front_axis_rotation(axis: str) -> np.ndarray:
    """--front-axis に応じて「+Z が正面」になるよう回す回転行列。"""
    axis = axis.lower()
    if axis in ("+z", "z"):
        return np.eye(3)
    if axis == "-z":
        return rot_y(180)
    if axis in ("+x", "x"):
        return rot_y(-90)
    if axis == "-x":
        return rot_y(90)
    return np.eye(3)


def load_mesh(path):
    m = trimesh.load(path, force="mesh")
    if not isinstance(m, trimesh.Trimesh):
        raise RuntimeError(f"メッシュとして読めません: {path}")
    return m


def camera_basis(d, up_hint):
    """カメラ方向 d(オブジェクト→カメラ)から right / up を作る。"""
    f = -d / np.linalg.norm(d)  # 視線方向(カメラ→オブジェクト)
    up = up_hint
    if abs(np.dot(f, up)) > 0.99:
        up = np.array([0.0, 0.0, -1.0])
    right = np.cross(f, up)
    right /= np.linalg.norm(right)
    true_up = np.cross(right, f)
    true_up /= np.linalg.norm(true_up)
    return right, true_up


def sample_image(img_arr, u, v):
    """u,v in [0,1] -> RGB (0-255). v=0 を画像上端に。"""
    h, w = img_arr.shape[:2]
    x = np.clip((u * (w - 1)).astype(int), 0, w - 1)
    y = np.clip(((1.0 - v) * (h - 1)).astype(int), 0, h - 1)
    return img_arr[y, x, :3]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mesh", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--view", action="append", default=[], help="name=path 形式")
    ap.add_argument("--front-axis", default="+z")
    ap.add_argument("--power", type=float, default=2.0, help="法線×カメラ方向の重み指数")
    args = ap.parse_args()

    views = {}
    for v in args.view:
        if "=" not in v:
            continue
        name, path = v.split("=", 1)
        name = name.strip().lower()
        if name not in BASE_DIRS:
            print(f"[multiview] 未知のビュー名をスキップ: {name}", file=sys.stderr)
            continue
        views[name] = path.strip()
    if not views:
        print("ERROR: --view が1つも指定されていません", file=sys.stderr)
        sys.exit(2)

    mesh = load_mesh(args.mesh)
    verts = mesh.vertices.view(np.ndarray).astype(np.float64)
    normals = mesh.vertex_normals.view(np.ndarray).astype(np.float64)

    # 正面軸の補正回転(法線・頂点の両方に適用してから投影)
    R = front_axis_rotation(args.front_axis)
    pv = verts @ R.T
    pn = normals @ R.T

    up_hint = np.array([0.0, 1.0, 0.0])
    n = len(verts)
    acc = np.zeros((n, 3), dtype=np.float64)
    wsum = np.zeros(n, dtype=np.float64)

    for name, path in views.items():
        d = BASE_DIRS[name]
        img = Image.open(path).convert("RGB")
        img_arr = np.asarray(img)
        right, true_up = camera_basis(d, up_hint)

        # 投影座標(カメラ平面)
        sx = pv @ right
        sy = pv @ true_up
        # メッシュのこのビューでの範囲をフレームいっぱいにマップ
        xmin, xmax = sx.min(), sx.max()
        ymin, ymax = sy.min(), sy.max()
        # アスペクト維持: 大きい方の範囲に合わせて正方化(写真は対象中心想定)
        cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
        half = max(xmax - xmin, ymax - ymin) / 2 * 1.02 + 1e-9
        u = (sx - (cx - half)) / (2 * half)
        vv = (sy - (cy - half)) / (2 * half)

        # 法線がカメラを向いている頂点だけ採用
        facing = pn @ d
        weight = np.clip(facing, 0.0, None) ** args.power

        cols = sample_image(img_arr, u, vv).astype(np.float64)
        acc += cols * weight[:, None]
        wsum += weight
        print(f"[multiview] 投影: {name} ({path}) 可視頂点={int((weight>0).sum())}/{n}")

    # どのビューからも見えない頂点はグレーで埋める
    covered = wsum > 1e-8
    colors = np.full((n, 3), 160.0)
    colors[covered] = acc[covered] / wsum[covered, None]
    colors = np.clip(colors, 0, 255).astype(np.uint8)

    rgba = np.concatenate([colors, np.full((n, 1), 255, dtype=np.uint8)], axis=1)
    mesh.visual = trimesh.visual.ColorVisuals(mesh=mesh, vertex_colors=rgba)

    # GLB で書き出し(頂点カラー埋め込み)
    mesh.export(args.out)
    print(f"[multiview] 書き出し: {args.out} (covered={int(covered.sum())}/{n})")


if __name__ == "__main__":
    main()
