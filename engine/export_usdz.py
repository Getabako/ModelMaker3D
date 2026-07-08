#!/usr/bin/env python3
"""GLB/FBX/OBJ -> USDZ 変換(Procreate などでテクスチャ編集できる自己完結形式)。

ヘッドレス Blender で実行する:
  /Applications/Blender.app/Contents/MacOS/Blender --background \
    --python engine/export_usdz.py -- --mesh model.glb --out model.usdz

- テクスチャ(画像)を USDZ 内に同梱する(export_textures_mode='NEW')。
- ワールド/背景色が紛れ込むのを防ぐ(convert_world_material=False)。
  これがあると Procreate でマテリアル読込が崩れ真っ白になることがある。
- 有料 API は一切使わない。Blender ローカルのみ。
"""
import bpy
import sys
import os


def argv_after_dashes():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def parse_args():
    a = argv_after_dashes()
    mesh = out = None
    i = 0
    while i < len(a):
        if a[i] == "--mesh":
            mesh = a[i + 1]; i += 2
        elif a[i] == "--out":
            out = a[i + 1]; i += 2
        else:
            i += 1
    return mesh, out


def main():
    mesh, out = parse_args()
    if not mesh or not out:
        print("ERROR: --mesh と --out は必須です", file=sys.stderr)
        sys.exit(2)
    mesh = os.path.abspath(mesh)
    out = os.path.abspath(out)
    if not out.lower().endswith(".usdz"):
        out += ".usdz"

    # まっさらなシーンから始める(既定の Cube/Camera/Light を排除)
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)

    ext = os.path.splitext(mesh)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=mesh)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=mesh)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=mesh)
    else:
        print(f"ERROR: 未対応の入力形式: {ext}", file=sys.stderr)
        sys.exit(2)

    # メッシュを全選択(selected_objects_only=True 用)
    for o in bpy.data.objects:
        o.select_set(o.type == "MESH")

    os.makedirs(os.path.dirname(out), exist_ok=True)
    bpy.ops.wm.usd_export(
        filepath=out,
        selected_objects_only=True,
        export_materials=True,
        export_uvmaps=True,
        export_textures_mode='NEW',     # 画像を USDZ 内に同梱
        overwrite_textures=True,
        convert_world_material=False,    # 背景色を exr として出さない(Procreate 白対策)
        generate_materialx_network=False,
        export_lights=False,
        export_cameras=False,
    )
    print(f"[export_usdz] OK -> {out}")


if __name__ == "__main__":
    main()
