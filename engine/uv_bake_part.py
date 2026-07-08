# パーツのジオメトリにキューブ投影UVを付け、各方向の画像を投影ベイクして
# 「6面正射図グリッド」の本物UVテクスチャ(アトラス)を作る。頂点カラーではなく
# 解像度がポリ数に依存しない2Dテクスチャなので、低ポリでも鮮明。
# 有料APIは使わない。conda env: triposr311 (trimesh, numpy, PIL)。
#
# 使い方:
#   python uv_bake_part.py --mesh dec.glb --views <DIR> --out model_uv.glb --atlas atlas.png \
#       [--front-axis +z] [--cell 1024]
#   <DIR> に front/right/back/left/top/bottom.png があれば使う(無い面はグレー)。
#
# 向きの規約(project_multiview と同じ): front=+Z, back=-Z, right=+X, left=-X, top=+Y, bottom=-Y。
import argparse, os, sys
import numpy as np
import trimesh
from PIL import Image

# 方向 -> カメラ方向(オブジェクト中心→カメラ)単位ベクトル
DIRS = {
    "front": np.array([0.0, 0.0, 1.0]),
    "right": np.array([1.0, 0.0, 0.0]),
    "back":  np.array([0.0, 0.0, -1.0]),
    "left":  np.array([-1.0, 0.0, 0.0]),
    "top":   np.array([0.0, 1.0, 0.0]),
    "bottom":np.array([0.0, -1.0, 0.0]),
}
# アトラス内のセル位置 (col,row)。3列×2行。
CELL = {
    "front": (0, 0), "right": (1, 0), "back": (2, 0),
    "left":  (0, 1), "top":   (1, 1), "bottom":(2, 1),
}
GRID_COLS, GRID_ROWS = 3, 2
GRAY = (138, 138, 138)


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
    true_up = np.cross(right, f); true_up /= np.linalg.norm(true_up)
    return right, true_up


def foreground_bbox(arr):
    """画像の前景(背景でない領域)の bbox を返す。背景は四隅の色から推定。
    返り値 (x0,y0,x1,y1)。前景が見つからなければ画像全体。"""
    h, w = arr.shape[:2]
    a = arr[:, :, :3].astype(np.int16)
    corners = np.stack([a[0, 0], a[0, w - 1], a[h - 1, 0], a[h - 1, w - 1]]).astype(np.int16)
    bg = np.median(corners, axis=0)
    dist = np.abs(a - bg).sum(axis=2)
    mask = dist > 36  # 背景との差がこれ以上を前景とみなす
    ys, xs = np.where(mask)
    if len(xs) < 50:
        return 0, 0, w, h
    pad = 2
    x0 = max(0, xs.min() - pad); x1 = min(w, xs.max() + 1 + pad)
    y0 = max(0, ys.min() - pad); y1 = min(h, ys.max() + 1 + pad)
    return x0, y0, x1, y1


def inpaint_background(arr, iters=24):
    """背景(四隅色に近い領域)を、前景の色で外側へ滲ませて埋める。
    シルエット端の面が背景(白)を拾って未塗りに見えるのを防ぐ。"""
    h, w = arr.shape[:2]
    a = arr[:, :, :3].astype(np.float32).copy()
    corners = np.stack([arr[0, 0], arr[0, w - 1], arr[h - 1, 0], arr[h - 1, w - 1]]).astype(np.float32)
    bg = np.median(corners, axis=0)
    known = (np.abs(a - bg).sum(axis=2) > 36)  # True=前景(確定色)
    for _ in range(iters):
        if known.all():
            break
        # 4近傍から既知色の平均を取り、未知画素を埋める
        acc = np.zeros_like(a); cnt = np.zeros((h, w), np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ks = np.roll(known, (dy, dx), (0, 1))
            vs = np.roll(a, (dy, dx), (0, 1))
            acc += vs * ks[:, :, None]; cnt += ks
        fillable = (~known) & (cnt > 0)
        a[fillable] = (acc[fillable] / cnt[fillable, None])
        known = known | fillable
    return np.clip(a, 0, 255).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mesh", required=True)
    ap.add_argument("--views", required=True, help="front/right/back/left/top/bottom.png のあるDIR")
    ap.add_argument("--out", required=True)
    ap.add_argument("--atlas", required=True)
    ap.add_argument("--front-axis", default="+z")
    ap.add_argument("--cell", type=int, default=1024)
    ap.add_argument("--atlas-in", default=None,
                    help="指定時はビューからベイクせず、この完成アトラスを貼る(Codex清書の再適用用)")
    ap.add_argument("--limb-fix", action="store_true",
                    help="人型向け: 頭頂/足裏以外の上下向き面を正面/背面に振り直す(腕の上下面のズレ・未塗り対策)")
    args = ap.parse_args()

    mesh = trimesh.load(args.mesh, force="mesh")
    if not isinstance(mesh, trimesh.Trimesh):
        print("ERROR: メッシュとして読めません", file=sys.stderr); sys.exit(2)
    # 各面が独立UVを持てるよう頂点を分離(継ぎ目で別UVにするため)
    mesh.unmerge_vertices()
    R = front_axis_rotation(args.front_axis)
    V = mesh.vertices.view(np.ndarray).astype(np.float64) @ R.T   # 回転後の頂点
    faces = mesh.faces.view(np.ndarray)
    fn = mesh.face_normals.view(np.ndarray).astype(np.float64) @ R.T

    # 各方向の投影基底と「実際の」投影範囲(正方形化しない=縦横比を保つ)。
    # メッシュの実バウンディングをセルいっぱいに線形マップ→画像前景と一致させる。
    proj = {}
    for name, d in DIRS.items():
        right, up = camera_basis(d)
        sx = V @ right; sy = V @ up
        sxmin, sxmax = float(sx.min()), float(sx.max())
        symin, symax = float(sy.min()), float(sy.max())
        rx = (sxmax - sxmin) or 1e-6; ry = (symax - symin) or 1e-6
        m = 0.012  # わずかな余白(縁の欠け防止)
        proj[name] = (right, up, sxmin - rx * m, sxmax + rx * m, symin - ry * m, symax + ry * m)

    # 画像を読み込み、前景(シルエット)をクロップしてセルいっぱいに貼る。無ければグレー。
    cell = args.cell
    if args.atlas_in:
        # 完成アトラスをそのまま使用(Codex清書の再適用)。サイズはグリッドに合わせる。
        a = Image.open(args.atlas_in).convert("RGB").resize((GRID_COLS * cell, GRID_ROWS * cell), Image.LANCZOS)
        atlas = np.asarray(a).copy()
        have = {n: True for n in DIRS}
    else:
        atlas = np.zeros((GRID_ROWS * cell, GRID_COLS * cell, 3), dtype=np.uint8)
        have = {}
        for name in DIRS:
            col, row = CELL[name]
            y0, x0 = row * cell, col * cell
            p = os.path.join(args.views, f"{name}.png")
            if os.path.exists(p):
                raw = np.asarray(Image.open(p).convert("RGB"))
                fx0, fy0, fx1, fy1 = foreground_bbox(raw)   # 前景に合わせてクロップ
                sub = inpaint_background(raw[fy0:fy1, fx0:fx1])  # 背景の白を前景色で埋める
                crop = Image.fromarray(sub).resize((cell, cell), Image.LANCZOS)
                atlas[y0:y0 + cell, x0:x0 + cell] = np.asarray(crop)
                have[name] = True
            else:
                atlas[y0:y0 + cell, x0:x0 + cell] = GRAY
                have[name] = False
                print(f"[uv_bake] {name}.png なし -> グレー", file=sys.stderr)

    # 各面の支配軸を選び、その方向のセルにUVを割り当てる(実バウンディング→セル線形)
    aw, ah = GRID_COLS * cell, GRID_ROWS * cell
    uv = np.zeros((len(mesh.vertices), 2), dtype=np.float64)
    names = list(DIRS.keys())
    dvecs = np.array([DIRS[n] for n in names])         # (6,3)
    dom = np.argmax(fn @ dvecs.T, axis=1)              # 各面の支配方向index
    idx = {n: i for i, n in enumerate(names)}
    if args.limb_fix:
        # up=+Y(回転後), front=+Z。頭頂/足裏ゾーン以外の上下向き面を front/back へ。
        fc = V[faces].mean(axis=1)                      # (F,3) 面中心(回転後)
        ymin, ymax = float(V[:, 1].min()), float(V[:, 1].max())
        H = (ymax - ymin) or 1e-6
        head_zone = fc[:, 1] > ymax - 0.20 * H
        feet_zone = fc[:, 1] < ymin + 0.12 * H
        for fi in range(len(faces)):
            nm = names[dom[fi]]
            if nm == "top" and not head_zone[fi]:
                dom[fi] = idx["front"] if fc[fi, 2] >= 0 else idx["back"]
            elif nm == "bottom" and not feet_zone[fi]:
                dom[fi] = idx["front"] if fc[fi, 2] >= 0 else idx["back"]
    for fi, face in enumerate(faces):
        name = names[dom[fi]]
        right, up, sxmin, sxmax, symin, symax = proj[name]
        col, row = CELL[name]
        for vi in face:
            p = V[vi]
            sx = p @ right; sy = p @ up
            u_local = (sx - sxmin) / (sxmax - sxmin)       # [0,1]
            v_local = (sy - symin) / (symax - symin)       # [0,1] (上が1)
            px = (col + np.clip(u_local, 0, 1)) * cell
            py = (row + (1.0 - np.clip(v_local, 0, 1))) * cell
            uv[vi, 0] = px / aw
            uv[vi, 1] = 1.0 - py / ah                       # glTF: V=0が下
    # 元の頂点へ回転を戻す必要はない(mesh.verticesはそのまま使う)
    img = Image.fromarray(atlas, "RGB")
    from trimesh.visual.material import PBRMaterial
    from trimesh.visual import TextureVisuals
    mat = PBRMaterial(baseColorTexture=img, metallicFactor=0.0, roughnessFactor=0.85)
    mesh.visual = TextureVisuals(uv=uv, material=mat, image=img)

    os.makedirs(os.path.dirname(os.path.abspath(args.atlas)), exist_ok=True)
    img.save(args.atlas)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    mesh.export(args.out)
    tri = len(faces)
    print(f"[uv_bake] OK -> {args.out} (tris={tri}, atlas={aw}x{ah}, views={[n for n in DIRS if have[n]]})")


if __name__ == "__main__":
    main()
