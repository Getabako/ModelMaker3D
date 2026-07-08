# Blender: モデルを Mixamo に通りやすい形へ整形して FBX 出力。
# 1メッシュ統合・原点を足元中央・適度なスケールにそろえる。
import bpy, sys, os, mathutils


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    d = {"mesh": None, "out": None, "scale": "1.0"}
    i = 0
    while i < len(a):
        if a[i] in ("--mesh", "--out", "--scale"):
            d[a[i][2:]] = a[i + 1]; i += 2
        else:
            i += 1
    return d


def main():
    a = args()
    bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete(use_global=False)
    e = os.path.splitext(a["mesh"])[1].lower()
    if e in (".glb", ".gltf"): bpy.ops.import_scene.gltf(filepath=a["mesh"])
    elif e == ".fbx": bpy.ops.import_scene.fbx(filepath=a["mesh"])
    elif e == ".obj": bpy.ops.wm.obj_import(filepath=a["mesh"])
    else: print("ERROR: unsupported", file=sys.stderr); sys.exit(2)

    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1: bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active

    # 足元中央を原点へ
    bb = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
    mn = mathutils.Vector((min(v[i] for v in bb) for i in range(3)))
    mx = mathutils.Vector((max(v[i] for v in bb) for i in range(3)))
    center = (mn + mx) / 2
    obj.location.x -= center.x
    obj.location.y -= center.y
    obj.location.z -= mn.z  # 足元を z=0
    # スケール調整
    s = float(a["scale"])
    if s != 1.0:
        obj.scale = (s, s, s)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    os.makedirs(os.path.dirname(a["out"]), exist_ok=True)
    bpy.ops.export_scene.fbx(filepath=a["out"], path_mode="COPY", embed_textures=True,
                             apply_unit_scale=True, object_types={"MESH"})
    print("[prep_mixamo] OK ->", a["out"])


if __name__ == "__main__":
    main()
