# Blender: メッシュを目標面数まで削減して書き出す(ジオメトリのみ)。
# 実行: blender --background --python decimate.py -- --mesh in.glb --out out.glb [--faces 120000]
import bpy, sys, os


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    d = {"mesh": None, "out": None, "faces": "120000"}
    i = 0
    while i < len(a):
        if a[i] in ("--mesh", "--out", "--faces"):
            d[a[i][2:]] = a[i + 1]; i += 2
        else:
            i += 1
    return d


def main():
    a = args()
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    e = os.path.splitext(a["mesh"])[1].lower()
    if e in (".glb", ".gltf"): bpy.ops.import_scene.gltf(filepath=a["mesh"])
    elif e == ".obj": bpy.ops.wm.obj_import(filepath=a["mesh"])
    else: print("ERROR unsupported", file=sys.stderr); sys.exit(2)
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1: bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    nf = len(obj.data.polygons)
    tf = int(a["faces"])
    if tf > 0 and nf > tf:
        m = obj.modifiers.new("dec", "DECIMATE"); m.ratio = max(0.01, tf / nf)
        bpy.ops.object.modifier_apply(modifier=m.name)
        print(f"[decimate] {nf} -> {len(obj.data.polygons)}")
    os.makedirs(os.path.dirname(a["out"]), exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=a["out"], export_format="GLB")
    print("[decimate] OK ->", a["out"])


if __name__ == "__main__":
    main()
