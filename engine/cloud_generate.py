# Colab(Hunyuan3D-2)の公開エンドポイントに画像を送り、高品質な3Dメッシュ(GLB)を受け取る。
# Colab Pro の GPU を使う(生成ごとの従量課金APIではなく、ユーザーのサブスク)。
# trycloudflare は約100秒でタイムアウト(524)するため、非同期ジョブAPI(/gen_async→/status→/result)を優先し、
# 旧サーバー(未対応)には同期 /gen へフォールバックする。
# conda env: triposr311 で実行(requests 必須)。
import sys
import os
import argparse
import json
import time

import requests

POLL_INTERVAL = 5       # 秒
POLL_TIMEOUT = 30 * 60  # 秒(A100 paint 4096 でも余裕を持って30分)
# localtunnel(固定URL)の確認ページをスキップするヘッダ。cloudflareには無害。
HEADERS = {"Bypass-Tunnel-Reminder": "1"}


def gen_async(endpoint, image_path, fields):
    """非同期ジョブAPI。旧サーバー(404)なら None を返す。"""
    with open(image_path, "rb") as f:
        files = {"image": (os.path.basename(image_path), f, "image/png")}
        r = requests.post(endpoint + "/gen_async", files=files, data=fields, timeout=120, headers=HEADERS)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    jid = r.json()["job"]
    print(f"[cloud] ジョブ開始: {jid} (5秒ごとにポーリング)")
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        try:
            s = requests.get(f"{endpoint}/status/{jid}", timeout=30, headers=HEADERS).json()
        except Exception as e:
            print(f"[cloud] status取得リトライ: {e}")
            continue
        st = s.get("status")
        if st == "done":
            res = requests.get(f"{endpoint}/result/{jid}", timeout=300, headers=HEADERS)
            res.raise_for_status()
            return res.content, dict(res.headers)
        if st == "error":
            raise RuntimeError(f"cloud生成エラー: {s.get('error')}")
        if st == "unknown":
            raise RuntimeError("cloudジョブが見つからない(Colabが再起動した可能性)")
    raise RuntimeError(f"cloud生成がタイムアウト({POLL_TIMEOUT}秒)")


def gen_sync(endpoint, image_path, fields):
    """旧サーバー互換の同期API(トンネルが100秒で切れる制約あり)。"""
    with open(image_path, "rb") as f:
        files = {"image": (os.path.basename(image_path), f, "image/png")}
        r = requests.post(endpoint + "/gen", files=files, data=fields, timeout=1200, headers=HEADERS)
    r.raise_for_status()
    return r.content, dict(r.headers)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", required=True, help="Colab の公開URL (例: https://xxxx.trycloudflare.com)")
    ap.add_argument("--image", required=True)
    ap.add_argument("--out", required=True, help="保存先(.glb)")
    ap.add_argument("--texture", default="auto", help="auto|shape (shape=形状のみ)")
    ap.add_argument("--steps", default="50")
    ap.add_argument("--octree", default="384", help="メッシュ精細度(256=標準,384=高,512=最高/A100向け)")
    args = ap.parse_args()

    endpoint = args.endpoint.rstrip("/")
    fields = {"texture": args.texture, "steps": args.steps, "octree": args.octree}
    print(f"[cloud] 送信: {endpoint}  image={args.image} (steps={args.steps}, octree={args.octree})")

    result = gen_async(endpoint, args.image, fields)
    if result is None:
        print("[cloud] 非同期API未対応の旧サーバー → 同期 /gen にフォールバック")
        result = gen_sync(endpoint, args.image, fields)
    content, headers = result

    with open(args.out, "wb") as f:
        f.write(content)

    textured = str(headers.get("X-Textured", headers.get("x-textured", "0"))) in ("1", "true", "True")
    meta = {"textured": textured, "bytes": len(content)}
    with open(os.path.splitext(args.out)[0] + "_meta.json", "w") as f:
        json.dump(meta, f)
    print(f"[cloud] 受信: {args.out} ({len(content)} bytes, textured={textured})")


if __name__ == "__main__":
    main()
