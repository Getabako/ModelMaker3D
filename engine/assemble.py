# Blender: parts.json のレイアウトに従って各パーツGLBを配置・スケールし、1つのモデルに統合する。
# 参照画像の正規化座標(cx,cy,w,h)を世界座標にマップ。x=横, y(画像下向き)→世界Z上方向, 奥行きはZ中心。
#
# 実行:
#   blender --background --python assemble.py -- --parts-json parts.json --parts-dir <dir> --out model.glb [--fbx model.fbx] [--height 2.0] [--aspect 1.0]
#   各パーツは <parts-dir>/<name>/model.glb を読み込む(無ければスキップ)。
import bpy, sys, os, json, math, mathutils


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    d = {"parts-json": None, "parts-dir": None, "out": None, "fbx": None, "height": "2.0", "aspect": "1.0",
         "model-name": "model.glb", "no-join": "0", "square-depth": "0"}
    i = 0
    while i < len(a):
        k = a[i]
        if k.startswith("--") and i + 1 < len(a):
            d[k[2:]] = a[i + 1]; i += 2
        else:
            i += 1
    return d


def clear():
    # デフォルトのCube/Camera/Light を含め、全オブジェクトを確実に削除する。
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)


def import_glb(path):
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.context.scene.objects if o not in before and o.type == "MESH"]
    if not new:
        return None
    bpy.ops.object.select_all(action="DESELECT")
    for o in new: o.select_set(True)
    bpy.context.view_layer.objects.active = new[0]
    if len(new) > 1:
        bpy.ops.object.join()
    return bpy.context.view_layer.objects.active


def bbox(obj):
    bb = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
    mn = mathutils.Vector((min(v[i] for v in bb) for i in range(3)))
    mx = mathutils.Vector((max(v[i] for v in bb) for i in range(3)))
    return mn, mx


def main():
    a = args()
    clear()  # デフォルトCube等を除去(混入防止)
    spec = json.load(open(a["parts-json"]))
    parts_dir = a["parts-dir"]
    H = float(a["height"])      # 世界での全体の高さ
    aspect = float(a["aspect"]) # 画像の幅/高さ
    placed = []

    overlap = float(a.get("overlap", "0.22"))  # 隣接パーツの縦の食い込み率(隙間を無くす)
    cursor_z = -H / 2.0                           # 下から積み上げる
    # order昇順(下→上)
    parts = sorted(spec["parts"], key=lambda p: p.get("order", 0))
    for p in parts:
        name = p["name"]
        glb = os.path.join(parts_dir, name, a.get("model-name", "model.glb"))
        if not os.path.exists(glb):
            print(f"[assemble] skip (no model): {name}")
            continue
        obj = import_glb(glb)
        if obj is None:
            print(f"[assemble] skip (empty): {name}")
            continue

        # 目標サイズ(世界): 画像正規化 w,h,depth をレイアウト箱として、非一様スケールで合わせる。
        # (各パーツのメッシュはほぼ立方体に正規化されているため、一様スケールだと
        #  全部同じ大きさの塊になり重なる。w×h×depth の箱に各軸独立で合わせる。)
        target_w = max(1e-4, float(p["w"])) * H * aspect       # 横(X)
        target_h = max(1e-4, float(p["h"])) * H                # 縦(Z, Blender上向き)
        sq = float(a.get("square-depth", "0"))
        if sq > 0:
            target_d = target_w * sq   # 奥行を幅×sq の正方形寄りに(浅すぎ対策)
        else:
            target_d = max(1e-4, float(p.get("depth", p["w"]))) * H  # 奥行(Y)
        mn, mx = bbox(obj)
        cur_x = max(1e-4, mx.x - mn.x)
        cur_z = max(1e-4, mx.z - mn.z)
        cur_y = max(1e-4, mx.y - mn.y)
        obj.scale = (target_w / cur_x, target_d / cur_y, target_h / cur_z)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        bpy.context.view_layer.update()

        # 横位置は画像cxから。縦位置は order順に下から積み上げ(隙間を作らない)。
        # center_x=1 なら対称建築として水平中心に揃える(各階の左右ズレを無くす)。
        if str(a.get("center-x", "0")) == "1":
            wx = 0.0
        else:
            wx = (float(p["cx"]) - 0.5) * H * aspect
        mn, mx = bbox(obj)
        ph = mx.z - mn.z
        wz = cursor_z + ph / 2.0
        cursor_z = cursor_z + ph * (1.0 - overlap)  # 次パーツは食い込ませる
        cur_center = (mn + mx) / 2
        obj.location.x += wx - cur_center.x
        obj.location.z += wz - cur_center.z
        obj.location.y += 0 - cur_center.y  # 奥行きは中心0
        bpy.context.view_layer.update()
        placed.append(obj)
        print(f"[assemble] placed {name}: box=({target_w:.2f}x{target_h:.2f}x{target_d:.2f}) z={wz:.2f}")

        # 位置を焼き込んだ単体ファイルを書き出す(0,0,0で読み込むだけで正しく並ぶ)。
        if str(a.get("export-placed", "0")) == "1":
            bpy.ops.object.select_all(action="DESELECT")
            obj.select_set(True)
            pp = os.path.join(parts_dir, name, "placed.glb")
            try:
                bpy.ops.export_scene.gltf(filepath=pp, export_format="GLB", use_selection=True,
                                          export_materials="EXPORT", export_image_format="AUTO")
            except Exception as e:
                print("[assemble] placed export skip:", name, e)

    if not placed:
        print("[assemble] ERROR: 配置できるパーツがありません", file=sys.stderr); sys.exit(1)

    # 統合(--no-join 1 なら各パーツを別オブジェクトのまま残す=手動編集向け)
    bpy.ops.object.select_all(action="DESELECT")
    for o in placed: o.select_set(True)
    bpy.context.view_layer.objects.active = placed[0]
    if str(a.get("no-join", "0")) != "1":
        bpy.ops.object.join()

    os.makedirs(os.path.dirname(a["out"]), exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=a["out"], export_format="GLB",
                              export_materials="EXPORT", export_image_format="AUTO")
    print("[assemble] GLB ->", a["out"])
    if a["fbx"]:
        bpy.ops.export_scene.fbx(filepath=a["fbx"], path_mode="COPY", embed_textures=True)
        print("[assemble] FBX ->", a["fbx"])


if __name__ == "__main__":
    main()
