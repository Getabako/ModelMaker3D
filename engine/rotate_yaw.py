# テクスチャ/UVを保持したままモデルをヨー回転(Z軸)して書き出す。
# 前後逆(verify_front NG)のcloudモデルを180°回すために使う。溶接等の破壊的処理はしない。
# 実行: blender --background --python rotate_yaw.py -- --mesh in.glb --out out.glb [--deg 180]
import sys
import math
import bpy


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:]
    a = {"deg": "180"}
    i = 0
    while i < len(argv):
        k = argv[i].lstrip("-")
        a[k] = argv[i + 1]
        i += 2
    return a


def main():
    a = parse_args()
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    e = a["mesh"].rsplit(".", 1)[-1].lower()
    if e in ("glb", "gltf"):
        bpy.ops.import_scene.gltf(filepath=a["mesh"])
    elif e == "obj":
        bpy.ops.wm.obj_import(filepath=a["mesh"])
    elif e == "fbx":
        bpy.ops.import_scene.fbx(filepath=a["mesh"])
    else:
        raise SystemExit(f"unsupported: {a['mesh']}")
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not objs:
        raise SystemExit("no mesh")
    rad = math.radians(float(a["deg"]))
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.rotation_euler[2] += rad
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    bpy.ops.export_scene.gltf(filepath=a["out"], export_format="GLB")
    print(f"[rotate_yaw] OK: {a['out']} (deg={a['deg']})")


main()
