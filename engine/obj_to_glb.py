# OBJ(頂点カラー付き) を GLB に変換する。TripoSR の頂点カラーをそのまま保持する。
# conda env: triposr311 (trimesh) で実行。
import sys
import trimesh

if len(sys.argv) < 3:
    print("usage: obj_to_glb.py <in.obj> <out.glb>", file=sys.stderr)
    sys.exit(2)

mesh = trimesh.load(sys.argv[1], force="mesh")
mesh.export(sys.argv[2])
try:
    n = len(mesh.visual.vertex_colors)
except Exception:
    n = 0
print(f"[obj_to_glb] {sys.argv[1]} -> {sys.argv[2]} (vertex_colors={n})")
