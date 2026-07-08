# Blender バックグラウンド実行スクリプト。
# TripoSR が出力したメッシュ(OBJ/GLB)に、Codex 画像生成で作ったテクスチャ画像を貼り付け、
# テクスチャ付き GLB(必要なら FBX も)を書き出す。有料APIは使わない。
#
# 実行例:
#   /Applications/Blender.app/Contents/MacOS/Blender --background --python apply_texture.py -- \
#       --mesh /path/mesh.obj --texture /path/texture.png --out /path/model.glb \
#       [--fbx /path/model.fbx] [--uv smart|sphere|view] [--keep-vertex-color]
#
# テクスチャの貼り方(--uv):
#   smart  : Smart UV Project。シームレス/PBRマテリアル系テクスチャ向け(既定)。
#   sphere : 球状投影。丸い・有機的なオブジェクト向け。
#   view   : 正面ビューから投影。正面写真ライクなテクスチャ向け(背面は引き伸ばし)。

import bpy
import sys
import os
import math


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    args = {
        "mesh": None,
        "texture": None,
        "out": None,
        "fbx": None,
        "uv": "smart",
        "keep_vertex_color": False,
    }
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--mesh": args["mesh"] = argv[i + 1]; i += 2
        elif a == "--texture": args["texture"] = argv[i + 1]; i += 2
        elif a == "--out": args["out"] = argv[i + 1]; i += 2
        elif a == "--fbx": args["fbx"] = argv[i + 1]; i += 2
        elif a == "--uv": args["uv"] = argv[i + 1]; i += 2
        elif a == "--keep-vertex-color": args["keep_vertex_color"] = True; i += 1
        else: i += 1
    return args


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.images):
        for b in list(block):
            block.remove(b)


def import_mesh(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    elif ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == ".ply":
        bpy.ops.wm.ply_import(filepath=path)
    else:
        raise RuntimeError(f"未対応のメッシュ形式: {ext}")
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not objs:
        raise RuntimeError("メッシュが読み込めませんでした")
    return objs


def join_objects(objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    return bpy.context.view_layer.objects.active


def unwrap(obj, mode):
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    if mode == "sphere":
        bpy.ops.uv.sphere_project()
    elif mode == "view":
        # 正面(-Y 方向を向くカメラ視点)から投影
        bpy.ops.uv.project_from_view(orthographic=True)
    else:
        bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")


def build_material(texture_path, keep_vertex_color):
    mat = bpy.data.materials.new(name="GeneratedTexture")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.7
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    tex = nodes.new("ShaderNodeTexImage")
    img = bpy.data.images.load(texture_path)
    tex.image = img
    links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])

    return mat


def assign_material(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def export_glb(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format="GLB",
        export_materials="EXPORT",
        export_image_format="AUTO",
    )


def export_fbx(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.export_scene.fbx(
        filepath=path,
        path_mode="COPY",
        embed_textures=True,
        mesh_smooth_type="FACE",
    )


def main():
    args = parse_args()
    if not args["mesh"] or not args["out"]:
        print("ERROR: --mesh と --out は必須です", file=sys.stderr)
        sys.exit(2)

    clear_scene()
    objs = import_mesh(args["mesh"])
    obj = join_objects(objs)

    if args["texture"]:
        unwrap(obj, args["uv"])
        mat = build_material(args["texture"], args["keep_vertex_color"])
        assign_material(obj, mat)
        print(f"[apply_texture] テクスチャ適用: {args['texture']} (uv={args['uv']})")
    else:
        print("[apply_texture] テクスチャなし(頂点カラーのまま出力)")

    export_glb(args["out"])
    print(f"[apply_texture] GLB 書き出し: {args['out']}")
    if args["fbx"]:
        export_fbx(args["fbx"])
        print(f"[apply_texture] FBX 書き出し: {args['fbx']}")


if __name__ == "__main__":
    main()
