# Smart UV展開済みメッシュに、全ビューを「法線で重み付けブレンド」して各テクセルへ焼く。
# キューブ投影(1面=1ビュー)と違い、各テクセルが向いている複数ビューだけを合成するので
# 隠れ面/曲面のズレ・誤ブリード・歪みが出にくい(Meshy方式に近い)。背景マスクで枠外も除外。
# 有料APIなし。conda env: triposr311 (trimesh, numpy, PIL)。
#
# 使い方:
#   python uv_bake_multiview.py --mesh uv.glb --views DIR --out model.glb --atlas tex.png \
#       [--front-axis +z] [--size 2048] [--power 3.0]
import argparse, os, sys
import numpy as np
import trimesh
from PIL import Image

DIRS = {
    "front": np.array([0.0, 0.0, 1.0]), "back": np.array([0.0, 0.0, -1.0]),
    "right": np.array([1.0, 0.0, 0.0]), "left": np.array([-1.0, 0.0, 0.0]),
    "top":   np.array([0.0, 1.0, 0.0]), "bottom": np.array([0.0, -1.0, 0.0]),
}


def rot_y(deg):
    r = np.radians(deg); c, s = np.cos(r), np.sin(r)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def front_axis_rotation(axis):
    axis = axis.lower()
    return {"+z": np.eye(3), "z": np.eye(3), "-z": rot_y(180),
            "+x": rot_y(-90), "x": rot_y(-90), "-x": rot_y(90)}.get(axis, np.eye(3))


def camera_basis(d, up_hint=np.array([0.0, 1.0, 0.0])):
    f = -d / np.linalg.norm(d)
    up = up_hint
    if abs(np.dot(f, up)) > 0.99:
        up = np.array([0.0, 0.0, -1.0])
    right = np.cross(f, up); right /= np.linalg.norm(right)
    tup = np.cross(right, f); tup /= np.linalg.norm(tup)
    return right, tup


def fg_bbox_mask(arr):
    h, w = arr.shape[:2]
    a = arr[:, :, :3].astype(np.int16)
    corners = np.stack([a[0, 0], a[0, w - 1], a[h - 1, 0], a[h - 1, w - 1]]).astype(np.int16)
    bg = np.median(corners, axis=0)
    dist = np.abs(a - bg).sum(axis=2)
    mask = dist > 36
    ys, xs = np.where(mask)
    if len(xs) < 50:
        return (0, 0, w, h), np.ones((h, w), bool)
    pad = 2
    x0 = max(0, xs.min() - pad); x1 = min(w, xs.max() + 1 + pad)
    y0 = max(0, ys.min() - pad); y1 = min(h, ys.max() + 1 + pad)
    return (x0, y0, x1, y1), mask


def inpaint_bg(arr, iters=24):
    h, w = arr.shape[:2]
    a = arr[:, :, :3].astype(np.float32).copy()
    corners = np.stack([arr[0, 0], arr[0, w - 1], arr[h - 1, 0], arr[h - 1, w - 1]]).astype(np.float32)
    bg = np.median(corners, axis=0)
    known = (np.abs(a - bg).sum(axis=2) > 36)
    for _ in range(iters):
        if known.all(): break
        acc = np.zeros_like(a); cnt = np.zeros((h, w), np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ks = np.roll(known, (dy, dx), (0, 1)); vs = np.roll(a, (dy, dx), (0, 1))
            acc += vs * ks[:, :, None]; cnt += ks
        fil = (~known) & (cnt > 0)
        a[fil] = acc[fil] / cnt[fil, None]; known = known | fil
    return np.clip(a, 0, 255).astype(np.uint8)


def sample(img, u, v):
    """u,v in [0,1] -> color. v=1 が画像上端。nearest。"""
    h, w = img.shape[:2]
    ix = np.clip((u * (w - 1)).astype(int), 0, w - 1)
    iy = np.clip(((1 - v) * (h - 1)).astype(int), 0, h - 1)
    return img[iy, ix]


def build_depth(V, faces, vw, D):
    """ビュー方向の深度バッファ(最前=最大 V·d)。隠れ面判定用。"""
    depth = np.full((D, D), -1e9, np.float64)
    sx = V @ vw["right"]; sy = V @ vw["up"]; dd = V @ vw["d"]
    u = (sx - vw["sxmin"]) / vw["rx"]; v = (sy - vw["symin"]) / vw["ry"]
    PX = u * (D - 1); PY = (1 - v) * (D - 1)
    for a, b, c in faces:
        x0, x1, x2 = PX[a], PX[b], PX[c]; y0, y1, y2 = PY[a], PY[b], PY[c]
        minx = int(max(0, np.floor(min(x0, x1, x2)))); maxx = int(min(D - 1, np.ceil(max(x0, x1, x2))))
        miny = int(max(0, np.floor(min(y0, y1, y2)))); maxy = int(min(D - 1, np.ceil(max(y0, y1, y2))))
        if maxx < minx or maxy < miny:
            continue
        gx, gy = np.meshgrid(np.arange(minx, maxx + 1) + 0.5, np.arange(miny, maxy + 1) + 0.5)
        den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(den) < 1e-9:
            continue
        l0 = ((y1 - y2) * (gx - x2) + (x2 - x1) * (gy - y2)) / den
        l1 = ((y2 - y0) * (gx - x2) + (x0 - x2) * (gy - y2)) / den
        l2 = 1 - l0 - l1
        ins = (l0 >= -0.001) & (l1 >= -0.001) & (l2 >= -0.001)
        if not ins.any():
            continue
        dval = l0 * dd[a] + l1 * dd[b] + l2 * dd[c]
        yy = (miny + np.where(ins)[0]); xx = (minx + np.where(ins)[1])
        cur = depth[yy, xx]
        better = dval[ins] > cur
        idx = np.where(better)[0]
        depth[yy[idx], xx[idx]] = dval[ins][idx]
    return depth


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mesh", required=True)
    ap.add_argument("--views", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--atlas", required=True)
    ap.add_argument("--front-axis", default="+z")
    ap.add_argument("--size", type=int, default=2048)
    ap.add_argument("--power", type=float, default=3.0)
    ap.add_argument("--cell", type=int, default=1024)
    args = ap.parse_args()

    mesh = trimesh.load(args.mesh, force="mesh", process=False)
    uv = np.asarray(mesh.visual.uv, dtype=np.float64)
    if uv is None or len(uv) != len(mesh.vertices):
        print("ERROR: UVが読めません", file=sys.stderr); sys.exit(2)
    R = front_axis_rotation(args.front_axis)
    V = mesh.vertices.view(np.ndarray).astype(np.float64) @ R.T
    N = mesh.vertex_normals.view(np.ndarray).astype(np.float64) @ R.T
    faces = mesh.faces.view(np.ndarray)

    # 各ビュー: 画像(前景クロップ+インペイント) と 前景マスク、投影範囲
    views = {}
    for name, d in DIRS.items():
        p = os.path.join(args.views, f"{name}.png")
        if not os.path.exists(p):
            continue
        raw = np.asarray(Image.open(p).convert("RGB"))
        (x0, y0, x1, y1), _ = fg_bbox_mask(raw)
        sub = raw[y0:y1, x0:x1]
        (_, _, _, _), m2 = fg_bbox_mask(sub)
        col = np.asarray(Image.fromarray(inpaint_bg(sub)).resize((args.cell, args.cell), Image.LANCZOS))
        msk = np.asarray(Image.fromarray((m2 * 255).astype(np.uint8)).resize((args.cell, args.cell), Image.NEAREST)) > 127
        right, up = camera_basis(d)
        sx = V @ right; sy = V @ up
        sxmin, sxmax = sx.min(), sx.max(); symin, symax = sy.min(), sy.max()
        rx = (sxmax - sxmin) or 1e-6; ry = (symax - symin) or 1e-6
        views[name] = dict(d=d, right=right, up=up, col=col, msk=msk,
                           sxmin=sxmin, rx=rx, symin=symin, ry=ry)
    if not views:
        print("ERROR: ビュー画像がありません", file=sys.stderr); sys.exit(2)

    # 隠れ面判定用の深度バッファ(各ビュー)。最前面のみ着色=ブリード防止(Meshy的)。
    DEPTH_RES = 1024
    diag = float(np.linalg.norm(V.max(0) - V.min(0)))
    dtol = diag * 0.008   # 厳しめ(回り込み防止)
    ymin, ymax = float(V[:, 1].min()), float(V[:, 1].max())
    Hy = (ymax - ymin) or 1e-6
    for name, vw in views.items():
        vw["depth"] = build_depth(V, faces, vw, DEPTH_RES)
        vw["dres"] = DEPTH_RES

    S = args.size
    acc = np.zeros((S, S, 3), np.float64)
    wsum = np.zeros((S, S), np.float64)
    px = uv[:, 0] * (S - 1)
    py = (1.0 - uv[:, 1]) * (S - 1)   # 画像row0=上

    # 三角形ごとにラスタライズ
    pw = float(args.power)
    for fi in range(len(faces)):
        a, b, c = faces[fi]
        x0p, x1p, x2p = px[a], px[b], px[c]
        y0p, y1p, y2p = py[a], py[b], py[c]
        minx = int(max(0, np.floor(min(x0p, x1p, x2p))));  maxx = int(min(S - 1, np.ceil(max(x0p, x1p, x2p))))
        miny = int(max(0, np.floor(min(y0p, y1p, y2p))));  maxy = int(min(S - 1, np.ceil(max(y0p, y1p, y2p))))
        if maxx < minx or maxy < miny:
            continue
        xs = np.arange(minx, maxx + 1) + 0.5
        ys = np.arange(miny, maxy + 1) + 0.5
        gx, gy = np.meshgrid(xs, ys)
        denom = (y1p - y2p) * (x0p - x2p) + (x2p - x1p) * (y0p - y2p)
        if abs(denom) < 1e-9:
            continue
        l0 = ((y1p - y2p) * (gx - x2p) + (x2p - x1p) * (gy - y2p)) / denom
        l1 = ((y2p - y0p) * (gx - x2p) + (x0p - x2p) * (gy - y2p)) / denom
        l2 = 1.0 - l0 - l1
        inside = (l0 >= -0.001) & (l1 >= -0.001) & (l2 >= -0.001)
        if not inside.any():
            continue
        b0 = l0[inside][:, None]; b1 = l1[inside][:, None]; b2 = l2[inside][:, None]
        P = b0 * V[a] + b1 * V[b] + b2 * V[c]
        Nrm = b0 * N[a] + b1 * N[b] + b2 * N[c]
        Nrm /= (np.linalg.norm(Nrm, axis=1, keepdims=True) + 1e-9)
        cols = np.zeros((P.shape[0], 3)); wts = np.zeros(P.shape[0])
        for name_v, v in views.items():
            facing = Nrm @ v["d"]
            w = np.clip(facing, 0, None) ** pw
            # top/bottom ビューは頭頂/足裏ゾーンの面だけに限定(腕/脚の上下面が頭頂図等を拾うのを防ぐ)
            if name_v == "top":
                w = w * (P[:, 1] > ymax - 0.18 * Hy)
            elif name_v == "bottom":
                w = w * (P[:, 1] < ymin + 0.12 * Hy)
            if not np.any(w > 0):
                continue
            u_l = (P @ v["right"] - v["sxmin"]) / v["rx"]
            vv_l = (P @ v["up"] - v["symin"]) / v["ry"]
            mvis = sample(v["msk"].astype(np.uint8), u_l, vv_l) > 0
            # 隠れ面判定: このテクセルがビューから実際に見えているか(最前面か)
            D = v["dres"]
            ix = np.clip((u_l * (D - 1)).astype(int), 0, D - 1)
            iy = np.clip(((1 - vv_l) * (D - 1)).astype(int), 0, D - 1)
            front_d = v["depth"][iy, ix]
            my_d = P @ v["d"]
            visible = my_d >= front_d - dtol
            w = w * mvis * visible
            c = sample(v["col"], u_l, vv_l).astype(np.float64)
            cols += c * w[:, None]; wts += w
        gi = np.where(inside)
        ay = (miny + gi[0]); ax = (minx + gi[1])
        acc[ay, ax] += cols
        wsum[ay, ax] += wts

    covered = wsum > 1e-8
    atlas = np.full((S, S, 3), 150.0)
    atlas[covered] = acc[covered] / wsum[covered, None]
    atlas = np.clip(atlas, 0, 255).astype(np.uint8)
    # 隙間/島の縁を周囲色で埋める(数px)
    known = covered.copy()
    a = atlas.astype(np.float32)
    for _ in range(28):
        if known.all(): break
        ac = np.zeros_like(a); cn = np.zeros((S, S), np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ks = np.roll(known, (dy, dx), (0, 1)); vs = np.roll(a, (dy, dx), (0, 1))
            ac += vs * ks[:, :, None]; cn += ks
        fil = (~known) & (cn > 0)
        a[fil] = ac[fil] / cn[fil, None]; known = known | fil
    atlas = np.clip(a, 0, 255).astype(np.uint8)

    img = Image.fromarray(atlas, "RGB")
    from trimesh.visual.material import PBRMaterial
    from trimesh.visual import TextureVisuals
    mat = PBRMaterial(baseColorTexture=img, metallicFactor=0.0, roughnessFactor=0.9)
    mesh.visual = TextureVisuals(uv=mesh.visual.uv, material=mat, image=img)
    os.makedirs(os.path.dirname(os.path.abspath(args.atlas)), exist_ok=True)
    img.save(args.atlas)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    mesh.export(args.out)
    print(f"[uv_mv] OK -> {args.out} (tex={S}, views={list(views)}, covered={int(covered.sum())}/{S*S})")


if __name__ == "__main__":
    main()
