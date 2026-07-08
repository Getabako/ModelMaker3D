# Blender: TripoSR等の単体メッシュを「立たせて・正面を向けて・溶接して・滑らかにして」書き出す。
# uv_bake は up=+Y / front=+Z(glTF) 前提。Blender内では up=+Z / front=-Y に相当。
# TripoSRの既定の向き(ヨー)はキャラごとにズレるため、ここで毎回:
#   1) 最長軸を高さ(+Z)に立てる
#   2) 腕幅(横に広い水平軸)を左右(X)へ、体の奥行き(顔の向き)をY軸へヨー整列
#   3) 正面判定(つま先=前 / 後頭部=後ろ のヒューリスティック多数決)で顔を -Y(=Blender正面ビュー)へ
# を自動適用する。手動上書きは --face (auto|keep|+x|-x|+y|-y)。
# 実行: blender --background --python stand_smooth.py -- --mesh in.obj --out out.glb [--smooth 16] [--face auto]
import bpy, sys, os, math, mathutils


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    d = {"mesh": None, "out": None, "smooth": "16", "face": "auto"}
    i = 0
    while i < len(a):
        if a[i] in ("--mesh", "--out", "--smooth", "--face"):
            d[a[i][2:]] = a[i + 1]; i += 2
        else:
            i += 1
    return d


def get_verts(m):
    """ローカル座標の頂点配列(N,3)を返す(matrix_worldはIdentity前提)。"""
    import numpy as np
    n = len(m.data.vertices)
    arr = np.empty(n * 3, dtype=np.float64)
    m.data.vertices.foreach_get("co", arr)
    return arr.reshape(n, 3)


def rotate_z(m, deg):
    m.data.transform(mathutils.Matrix.Rotation(math.radians(deg), 4, 'Z')); m.data.update()


def detect_front_sign_y(m):
    """立って腕幅=X・顔向き=Y に整列済みのメッシュで、正面が +Y か -Y かを推定。
    戻り値: +1(正面が+Y) / -1(正面が-Y)。つま先=前, 後頭部=後ろ を多数決。"""
    import numpy as np
    V = get_verts(m)
    zmin, zmax = V[:, 2].min(), V[:, 2].max(); H = (zmax - zmin) or 1e-6
    ymin, ymax = V[:, 1].min(), V[:, 1].max(); cyc = (ymin + ymax) / 2.0

    score = 0.0
    # 足元(つま先は前に張り出す): 下部18%の重心Yが寄る側=正面
    feet = V[V[:, 2] < zmin + 0.18 * H]
    if len(feet) > 30:
        score += 1.0 * np.sign(feet[:, 1].mean() - cyc)
    # 頭頂部(後頭部が後ろへ膨らむ): 上部28%の重心Yが寄る側=背面 → 反対が正面
    head = V[V[:, 2] > zmax - 0.28 * H]
    if len(head) > 30:
        score += 0.7 * (-np.sign(head[:, 1].mean() - cyc))
    # 顔の中段(鼻/あご)が最も前へ出る: 中段40〜75%で最前(|Y|最大)の符号
    mid = V[(V[:, 2] > zmin + 0.40 * H) & (V[:, 2] < zmin + 0.75 * H)]
    if len(mid) > 30:
        far = mid[np.argmax(np.abs(mid[:, 1] - cyc))]
        score += 0.5 * np.sign(far[1] - cyc)

    if score == 0:
        return -1  # 不明なら -Y を正面とみなす(既定の焼き規約に一致)
    return 1 if score > 0 else -1


def dims_from_verts(m):
    """m.dimensions は data.transform 直後に更新が遅れるため、頂点から実測する。"""
    V = get_verts(m)
    return V.max(0) - V.min(0)  # (dx, dy, dz)


def orient_face_front(m, face):
    """顔を -Y(Blender正面ビュー/ glTF +Z)へ向ける。face: auto|keep|+x|-x|+y|-y"""
    if face == "keep":
        return "keep"
    # 1) 腕幅(広い水平軸)を X へ。facing を Y へ。
    dx, dy, dz = dims_from_verts(m)
    if dy > dx:
        rotate_z(m, 90)  # Y(幅) -> X
    # 2) 正面の符号を決めて -Y へ
    if face == "auto":
        s = detect_front_sign_y(m)          # +1: 正面が+Y, -1: 正面が-Y
        if s > 0:
            rotate_z(m, 180)                # 正面を -Y へ
        return "auto(front->-Y)"
    if face == "flip":
        # 正面照合ゲートNG時のリトライ用: 自動判定の逆を採用する
        s = detect_front_sign_y(m)
        if s < 0:
            rotate_z(m, 180)
        return "flip(auto逆)"
    # 手動: 現在の顔向き軸を指定 → それを -Y へ回す
    cur = {"-y": 0, "+y": 180, "+x": -90, "-x": 90}.get(face.lower())
    if cur is None:
        s = detect_front_sign_y(m)
        if s > 0: rotate_z(m, 180)
        return "auto(bad --face)"
    rotate_z(m, cur)
    return f"manual({face})"


def main():
    a = args()
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    e = os.path.splitext(a["mesh"])[1].lower()
    if e in (".glb", ".gltf"): bpy.ops.import_scene.gltf(filepath=a["mesh"])
    elif e == ".obj": bpy.ops.wm.obj_import(filepath=a["mesh"])
    elif e == ".fbx": bpy.ops.import_scene.fbx(filepath=a["mesh"])
    else: print("ERROR unsupported", file=sys.stderr); sys.exit(2)

    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1: bpy.ops.object.join()
    m = bpy.context.view_layer.objects.active
    m.matrix_world = mathutils.Matrix.Identity(4)

    # 浮遊ゴミ除去: 分離パーツに分けて、最大パーツの30%未満の対角サイズの破片
    # (ベールの切れ端・リボン片など)を削除してから向き判定・スムーズへ進む。
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.separate(type='LOOSE')
    bpy.ops.object.mode_set(mode='OBJECT')
    parts = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if len(parts) > 1:
        def part_diag(o):
            bb = [o.matrix_world @ mathutils.Vector(c) for c in o.bound_box]
            mn = mathutils.Vector((min(v[i] for v in bb) for i in range(3)))
            mx = mathutils.Vector((max(v[i] for v in bb) for i in range(3)))
            return (mx - mn).length
        dmax = max(part_diag(o) for o in parts)
        drop = [o for o in parts if part_diag(o) < 0.30 * dmax]
        for o in drop:
            bpy.data.objects.remove(o, do_unlink=True)
        parts = [o for o in bpy.context.scene.objects if o.type == "MESH"]
        print(f"[stand_smooth] debris removed: {len(drop)} parts (kept {len(parts)})")
        bpy.ops.object.select_all(action="DESELECT")
        for o in parts: o.select_set(True)
        bpy.context.view_layer.objects.active = parts[0]
        if len(parts) > 1: bpy.ops.object.join()
        m = bpy.context.view_layer.objects.active

    # 最長軸を高さ(+Z)に立てる。TripoSRは高さがX軸で横倒しになりがち。
    d = m.dimensions
    if d.x >= d.y and d.x >= d.z:
        m.data.transform(mathutils.Matrix.Rotation(math.radians(-90), 4, 'Y'))  # X->Z
    elif d.y >= d.x and d.y >= d.z:
        m.data.transform(mathutils.Matrix.Rotation(math.radians(90), 4, 'X'))   # Y->Z
    m.data.update()

    # 顔を正面(-Y)へ自動整列(毎回)。
    mode = orient_face_front(m, a.get("face", "auto"))

    # 溶接(分離頂点を結合してスムーズが効くように)
    bpy.ops.object.select_all(action="DESELECT"); m.select_set(True)
    bpy.context.view_layer.objects.active = m
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.remove_doubles(threshold=0.0008)
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode='OBJECT')

    # スムーズ化
    it = int(a["smooth"])
    if it > 0:
        sm = m.modifiers.new("smooth", "SMOOTH"); sm.factor = 0.5; sm.iterations = it
        bpy.ops.object.modifier_apply(modifier=sm.name)
    bpy.ops.object.shade_smooth()
    try: bpy.ops.object.shade_auto_smooth(angle=math.radians(60))
    except Exception as ex: print("auto_smooth skip:", ex)

    # 足元を z=0、xy中心を原点へ
    bb = [m.matrix_world @ mathutils.Vector(c) for c in m.bound_box]
    mn = mathutils.Vector((min(v[i] for v in bb) for i in range(3)))
    mx = mathutils.Vector((max(v[i] for v in bb) for i in range(3)))
    T = mathutils.Matrix.Translation((-(mn.x + mx.x) / 2, -(mn.y + mx.y) / 2, -mn.z))
    m.data.transform(T); m.data.update()

    os.makedirs(os.path.dirname(a["out"]), exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=a["out"], export_format="GLB", use_selection=True)
    print("[stand_smooth] OK ->", a["out"], "dims=", tuple(round(x, 3) for x in m.dimensions), "face=", mode)


if __name__ == "__main__":
    main()
