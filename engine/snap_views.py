# GLBを正面(-Y)/背面(+Y)/左右からスナップショットする検証用スクリプト
# blender --background --python snap_views.py -- --mesh model.glb --out DIR [--prefix name]
import bpy, sys, os, math, mathutils


def args():
    argv = sys.argv[sys.argv.index("--") + 1:]
    d = {"mesh": None, "out": None, "prefix": "snap"}
    i = 0
    while i < len(argv):
        if argv[i] in ("--mesh", "--out", "--prefix"):
            d[argv[i][2:]] = argv[i + 1]; i += 2
        else:
            i += 1
    return d


a = args()
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.import_scene.gltf(filepath=a["mesh"])
objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
mn = mathutils.Vector((1e9,) * 3); mx = mathutils.Vector((-1e9,) * 3)
for o in objs:
    for c in o.bound_box:
        w = o.matrix_world @ mathutils.Vector(c)
        mn = mathutils.Vector(map(min, mn, w)); mx = mathutils.Vector(map(max, mx, w))
ctr = (mn + mx) / 2
size = max(mx - mn)
dist = size * 2.2

scene = bpy.context.scene
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "FLAT"
scene.display.shading.color_type = "TEXTURE"
scene.render.resolution_x = 512
scene.render.resolution_y = 512
scene.render.film_transparent = True

cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
scene.collection.objects.link(cam)
scene.camera = cam
cam.data.type = "ORTHO"
cam.data.ortho_scale = size * 1.2

views = {  # Blender座標: 正面=-Y側から見る
    "front": mathutils.Vector((0, -dist, 0)),
    "back": mathutils.Vector((0, dist, 0)),
    "right": mathutils.Vector((dist, 0, 0)),
    "left": mathutils.Vector((-dist, 0, 0)),
}
for name, off in views.items():
    cam.location = ctr + off
    d = (ctr - cam.location).normalized()
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = os.path.join(a["out"], f"{a['prefix']}_{name}.png")
    bpy.ops.render.render(write_still=True)
print("[snap_views] OK")
