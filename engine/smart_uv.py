# Blender(ヘッドレス): メッシュをSmart UV Projectで展開し、UV付きでglb書き出し。
# uv_bake_multiview.py の前段。実行:
#   blender --background --python smart_uv.py -- --mesh in.glb --out out_uv.glb [--angle 70] [--margin 0.002]
import bpy, sys, os, math


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    d = {"mesh": None, "out": None, "angle": "70", "margin": "0.002"}
    i = 0
    while i < len(a):
        if a[i] in ("--mesh", "--out", "--angle", "--margin"):
            d[a[i][2:]] = a[i + 1]; i += 2
        else:
            i += 1
    return d


def run_uv():
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(float(A["angle"])),
                             island_margin=float(A["margin"]), area_weight=0.0)
    try:
        bpy.ops.uv.pack_islands(margin=0.002)
    except Exception as e:
        print("pack skip:", e)
    bpy.ops.object.mode_set(mode='OBJECT')


def main():
    global A
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

    # まず通常コンテキストで、ダメなら一時ウィンドウ/エリアでoverride
    try:
        run_uv()
    except Exception as e1:
        print("[smart_uv] direct失敗→override試行:", e1)
        win = bpy.context.window_manager.windows[0] if bpy.context.window_manager.windows else None
        done = False
        if win:
            for area in win.screen.areas:
                if area.type == 'VIEW_3D':
                    for region in area.regions:
                        if region.type == 'WINDOW':
                            with bpy.context.temp_override(window=win, area=area, region=region):
                                run_uv(); done = True
                            break
        if not done:
            print("ERROR: smart_project不可(ヘッドレスにVIEW_3Dなし)", file=sys.stderr); sys.exit(3)

    os.makedirs(os.path.dirname(A["out"]), exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT"); m.select_set(True)
    bpy.ops.export_scene.gltf(filepath=A["out"], export_format="GLB", use_selection=True)
    print("[smart_uv] OK ->", A["out"], "uv:", [l.name for l in m.data.uv_layers])


if __name__ == "__main__":
    main()
