# Colab(Hunyuan3D-2)の公開エンドポイントに画像を送り、高品質な3Dメッシュ(GLB)を受け取る。
# Colab Pro の GPU を使う(生成ごとの従量課金APIではなく、ユーザーのサブスク)。
# conda env: triposr311 で実行(requests があれば使い、無ければ urllib)。
import sys
import os
import argparse
import json
import uuid
import mimetypes


def post_multipart(url, image_path, fields):
    """requests があれば使う。無ければ urllib で multipart を組む。"""
    try:
        import requests  # type: ignore
        with open(image_path, "rb") as f:
            files = {"image": (os.path.basename(image_path), f, "image/png")}
            r = requests.post(url, files=files, data=fields, timeout=1200)
        r.raise_for_status()
        return r.content, dict(r.headers)
    except ImportError:
        import urllib.request
        boundary = uuid.uuid4().hex
        with open(image_path, "rb") as f:
            img = f.read()
        ctype = mimetypes.guess_type(image_path)[0] or "image/png"
        body = b""
        for k, v in fields.items():
            body += f"--{boundary}\r\n".encode()
            body += f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="image"; filename="{os.path.basename(image_path)}"\r\n'.encode()
        body += f"Content-Type: {ctype}\r\n\r\n".encode() + img + b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        req = urllib.request.Request(url, data=body, headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        })
        with urllib.request.urlopen(req, timeout=1200) as resp:
            return resp.read(), dict(resp.headers)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", required=True, help="Colab の公開URL (例: https://xxxx.trycloudflare.com)")
    ap.add_argument("--image", required=True)
    ap.add_argument("--out", required=True, help="保存先(.glb)")
    ap.add_argument("--texture", default="auto", help="auto|shape (shape=形状のみ)")
    ap.add_argument("--steps", default="50")
    ap.add_argument("--octree", default="384", help="メッシュ精細度(256=標準,384=高,512=最高/A100向け)")
    args = ap.parse_args()

    url = args.endpoint.rstrip("/") + "/gen"
    print(f"[cloud] 送信: {url}  image={args.image} (steps={args.steps}, octree={args.octree})")
    content, headers = post_multipart(url, args.image, {"texture": args.texture, "steps": args.steps, "octree": args.octree})

    with open(args.out, "wb") as f:
        f.write(content)

    textured = str(headers.get("X-Textured", headers.get("x-textured", "0"))) in ("1", "true", "True")
    meta = {"textured": textured, "bytes": len(content)}
    with open(os.path.splitext(args.out)[0] + "_meta.json", "w") as f:
        json.dump(meta, f)
    print(f"[cloud] 受信: {args.out} ({len(content)} bytes, textured={textured})")


if __name__ == "__main__":
    main()
