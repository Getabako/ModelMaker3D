# Blender: 1パーツのメッシュに「本物のUVテクスチャ」を付ける。
# 正面(パーツ単体)画像を、指定軸からの平面投影UVとして割り当てる。
# UVは Python で直接計算する(project_from_view はヘッドレスでは使えないため)。
#
# 実行:
#   blender --background --python bake_part.py -- --mesh part.glb --image front.png --out part_tex.glb [--axis +z]
import bpy, sys, os, mathutils
import numpy as np


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    d = {"mesh": None, "image": None, "out": None, "axis": "+z", "faces": "60000"}
    i = 0
    while i < len(a):
        if a[i] in ("--mesh", "--image", "--out", "--axis", "--faces"):
            d[a[i][2:]] = a[i + 1]; i += 2
        else:
            i += 1
    return d


def decimate(obj, target_faces):
    """パーツは高密度すぎるので目標面数まで削減(軽量化・統合を扱いやすく)。"""
    nf = len(obj.data.polygons)
    if target_faces <= 0 or nf <= target_faces:
        return
    m = obj.modifiers.new("dec", "DECIMATE")
    m.ratio = max(0.01, float(target_faces) / nf)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=m.name)
    print(f"[bake_part] decimate {nf} -> {len(obj.data.polygons)} faces")


def clear():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for c in (bpy.data.meshes, bpy.data.materials, bpy.data.images):
        for b in list(c):
            c.remove(b)


def imp(path):
    e = os.path.splitext(path)[1].lower()
    if e == ".obj": bpy.ops.wm.obj_import(filepath=path)
    elif e in (".glb", ".gltf"): bpy.ops.import_scene.gltf(filepath=path)
    elif e == ".ply": bpy.ops.wm.ply_import(filepath=path)
    else: raise RuntimeError("unsupported: " + e)
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1: bpy.ops.object.join()
    return bpy.context.view_layer.objects.active


def planar_uv(obj, axis):
    """指定軸を正面とみなし、その平面へ平行投影した UV を numpy で高速計算して割り当てる。"""
    # ワールド変換を確定させてローカル=ワールドにする(以後 co をそのまま使える)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    me = obj.data
    nv = len(me.vertices)
    co = np.empty(nv * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    x, y, z = co[:, 0], co[:, 1], co[:, 2]

    def nz(a):
        lo, hi = a.min(), a.max()
        return np.zeros_like(a) if hi - lo < 1e-9 else (a - lo) / (hi - lo)

    ux, uz = nz(x), nz(z)
    if axis == "+z":   u = ux
    elif axis == "-z": u = 1.0 - ux
    elif axis == "+x": u = 1.0 - uz
    elif axis == "-x": u = uz
    else:              u = ux
    v = nz(y)
    vert_uv = np.stack([u, v], axis=1)  # (nv,2)

    nl = len(me.loops)
    lidx = np.empty(nl, dtype=np.int64)
    me.loops.foreach_get("vertex_index", lidx)
    loop_uv = vert_uv[lidx].reshape(-1)  # (nl*2,)

    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    me.uv_layers.active.data.foreach_set("uv", loop_uv)
    me.update()


def make_mat(image_path):
    mat = bpy.data.materials.new("PartTex"); mat.use_nodes = True
    nt = mat.node_tree; nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.inputs["Roughness"].default_value = 0.75
    tex = nt.nodes.new("ShaderNodeTexImage"); tex.image = bpy.data.images.load(image_path)
    uvn = nt.nodes.new("ShaderNodeUVMap"); uvn.uv_map = "UVMap"
    nt.links.new(uvn.outputs["UV"], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def main():
    a = args()
    if not a["mesh"] or not a["image"] or not a["out"]:
        print("ERROR: --mesh --image --out 必須", file=sys.stderr); sys.exit(2)
    clear()
    obj = imp(a["mesh"])
    decimate(obj, int(a["faces"]))
    planar_uv(obj, a["axis"])
    obj.data.materials.clear()
    obj.data.materials.append(make_mat(a["image"]))
    os.makedirs(os.path.dirname(a["out"]), exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=a["out"], export_format="GLB",
                              export_materials="EXPORT", export_image_format="AUTO")
    print("[bake_part] OK ->", a["out"])


if __name__ == "__main__":
    main()
