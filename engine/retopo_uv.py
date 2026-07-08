# Blender(ヘッドレス): AI生成メッシュを QuadriFlow でクワッド化(リトポ)→Smart UV展開→
# glb書き出し＋UVレイアウトPNG(手描き用の下絵)を出力。
# 実行: blender --background --python retopo_uv.py -- --mesh in.glb --out out_uv.glb --layout uv.png \
#       [--faces 6000] [--angle 66] [--margin 0.003] [--layout-size 2048] [--no-retopo]
import bpy, sys, os, math


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    d = {"mesh": None, "out": None, "layout": None, "faces": "6000",
         "angle": "66", "margin": "0.003", "layout-size": "2048", "no-retopo": "0", "voxel": "0.012"}
    i = 0
    while i < len(a):
        k = a[i]
        if k == "--no-retopo":
            d["no-retopo"] = "1"; i += 1
        elif k.startswith("--") and i + 1 < len(a):
            d[k[2:]] = a[i + 1]; i += 2
        else:
            i += 1
    return d


def draw_layout(m, path, size):
    """UV配線をPNGに描く(手描き下絵)。PILで各面のUVポリゴンを線描き。"""
    from PIL import Image, ImageDraw
    uvl = m.data.uv_layers.active.data
    img = Image.new("RGB", (size, size), (40, 40, 40))
    dr = ImageDraw.Draw(img)
    for poly in m.data.polygons:
        pts = []
        for li in poly.loop_indices:
            u, v = uvl[li].uv
            pts.append((u * (size - 1), (1 - v) * (size - 1)))
        if len(pts) >= 2:
            dr.line(pts + [pts[0]], fill=(230, 150, 60), width=1)
    img.save(path)


def main():
    A = args()
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    e = os.path.splitext(A["mesh"])[1].lower()
    if e in (".glb", ".gltf"): bpy.ops.import_scene.gltf(filepath=A["mesh"])
    elif e == ".obj": bpy.ops.wm.obj_import(filepath=A["mesh"])
    else: print("ERROR unsupported", file=sys.stderr); sys.exit(2)
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1: bpy.ops.object.join()
    m = bpy.context.view_layer.objects.active
    print("[retopo_uv] in faces:", len(m.data.polygons))

    if A["no-retopo"] != "1":
        # 先にVoxelリメッシュで多様体化(AI生成メッシュは非多様体でQuadriFlowがキャンセルされるため)
        vox = float(A["voxel"])
        if vox > 0:
            try:
                mod = m.modifiers.new("vox", "REMESH"); mod.mode = "VOXEL"
                mod.voxel_size = vox; mod.adaptivity = 0.0
                bpy.ops.object.modifier_apply(modifier=mod.name)
                print("[retopo_uv] voxel remesh faces:", len(m.data.polygons))
            except Exception as ex:
                print("[retopo_uv] voxel失敗:", ex)
        before = len(m.data.polygons)
        try:
            r = bpy.ops.object.quadriflow_remesh(target_faces=int(A["faces"]),
                                                 use_preserve_sharp=False, use_preserve_boundary=False,
                                                 smooth_normals=True)
            print("[retopo_uv] quadriflow", r, "faces:", before, "->", len(m.data.polygons))
        except Exception as ex:
            print("[retopo_uv] quadriflow失敗(元トポロジーで続行):", ex)

    # Smart UV 展開 + パック
    bpy.ops.object.shade_smooth()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(float(A["angle"])),
                             island_margin=float(A["margin"]), area_weight=0.0)
    try:
        bpy.ops.uv.pack_islands(margin=0.003)
    except Exception as ex:
        print("pack skip:", ex)
    bpy.ops.object.mode_set(mode='OBJECT')

    os.makedirs(os.path.dirname(os.path.abspath(A["out"])), exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT"); m.select_set(True)
    bpy.ops.export_scene.gltf(filepath=A["out"], export_format="GLB", use_selection=True)
    if A["layout"]:
        draw_layout(m, A["layout"], int(A["layout-size"]))
    print("[retopo_uv] OK ->", A["out"], "faces:", len(m.data.polygons),
          "uv:", [l.name for l in m.data.uv_layers])


if __name__ == "__main__":
    main()
