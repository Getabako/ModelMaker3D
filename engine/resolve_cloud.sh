#!/bin/bash
# Colabエンドポイントの自動解決。生きているURLを stdout に1行出す。見つからなければ exit 1。
# 優先順: 1) ~/.modelmaker3d_cloud の保存URL  2) 固定localtunnel URL(Colab側が起動していれば常に同じ)
# 固定URLが生きていたら ~/.modelmaker3d_cloud も更新する(以後の手貼り不要)。
set -u
FIXED_URL="https://mm3d-getabako.loca.lt"

alive() {
  curl -s -m 8 -H 'Bypass-Tunnel-Reminder: 1' "$1/health" 2>/dev/null | grep -q '"ok"'
}

SAVED=""
[[ -f "$HOME/.modelmaker3d_cloud" ]] && SAVED="$(tr -d '[:space:]' < "$HOME/.modelmaker3d_cloud")"
if [[ -n "$SAVED" ]] && alive "$SAVED"; then
  echo "$SAVED"
  exit 0
fi
if alive "$FIXED_URL"; then
  echo "$FIXED_URL" > "$HOME/.modelmaker3d_cloud"
  echo "$FIXED_URL"
  exit 0
fi
exit 1
