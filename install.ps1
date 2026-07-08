# ModelMaker3D — Windows one-line installer & launcher
#
# 1 行 (PowerShell):
#   iwr -useb https://raw.githubusercontent.com/Getabako/ModelMaker3D/main/install.ps1 | iex
#
# 何度貼っても OK。初回は全部インストール、2 回目以降は最新版に更新して起動。

$ErrorActionPreference = "Stop"

$GH_REPO    = if ($env:MODELMAKER3D_REPO)   { $env:MODELMAKER3D_REPO }   else { "Getabako/ModelMaker3D" }
$BRANCH     = if ($env:MODELMAKER3D_BRANCH) { $env:MODELMAKER3D_BRANCH } else { "main" }
# インストール先：デスクトップにわかりやすく置く（隠しフォルダにしない）。
$DesktopDir = [Environment]::GetFolderPath('Desktop')
$InstallDir = if ($env:MODELMAKER3D_APP_HOME) { $env:MODELMAKER3D_APP_HOME } else { Join-Path $DesktopDir "ModelMaker3DApp" }

function Info($msg) { Write-Host $msg -ForegroundColor Cyan }
function OK($msg)   { Write-Host $msg -ForegroundColor Green }
function Err($msg)  { Write-Host $msg -ForegroundColor Red }

Info "▶ ModelMaker3D セットアップを開始します（Windows）"

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Err "✗ winget が見つかりません。Windows 10/11 (build 1809+) で Microsoft Store から 'App Installer' を入れてください。"
    exit 1
}

function Ensure-Pkg($cmd, $wingetId, $label) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Info "▶ $label をインストールします"
        winget install --id $wingetId -e --silent --accept-source-agreements --accept-package-agreements
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    }
}

Ensure-Pkg "node" "OpenJS.NodeJS.LTS" "Node.js (LTS)"
Ensure-Pkg "git"  "Git.Git"           "Git"

if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
    Info "▶ Codex CLI をインストールします"
    npm install -g @openai/codex
}

if (Test-Path "$InstallDir\.git") {
    # ローカルで修正している人の変更を消さないよう、未コミット修正があれば
    # 自動更新（reset --hard）をスキップして保持する。
    $dirty = git -C $InstallDir status --porcelain
    if ($dirty) {
        Info "▶ あなたの修正を保持したまま起動します（自動更新はスキップ）"
        Info "  最新版に戻したい時は: cd `"$InstallDir`" ; git reset --hard origin/$BRANCH"
    } else {
        Info "▶ 既存のアプリを最新版に更新します"
        git -C $InstallDir fetch --quiet origin $BRANCH
        git -C $InstallDir reset --quiet --hard "origin/$BRANCH"
    }
} else {
    Info "▶ アプリをダウンロードします → $InstallDir"
    if (Test-Path $InstallDir) { Remove-Item -Recurse -Force $InstallDir }
    git clone --quiet --depth 1 --branch $BRANCH "https://github.com/$GH_REPO.git" $InstallDir
}

Set-Location $InstallDir

# 依存と本番ビルド（コミットが変わった or 成果物が無いなら再ビルド）
$CurSha = git -C $InstallDir rev-parse HEAD
$MarkFile = Join-Path $InstallDir ".next\.built-sha"
$LastSha = if (Test-Path $MarkFile) { Get-Content $MarkFile -ErrorAction SilentlyContinue } else { "" }

$NeedBuild = $false
if (-not (Test-Path (Join-Path $InstallDir "node_modules")))                 { $NeedBuild = $true }
if (-not (Test-Path (Join-Path $InstallDir ".next\standalone\server.js")))   { $NeedBuild = $true }
if ($CurSha -ne $LastSha)                                                     { $NeedBuild = $true }

if ($NeedBuild) {
    Info "▶ アプリを準備中（初回 or 更新があった時のみ・30 秒〜1 分）"
    npm install --silent
    npm run build | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir ".next") | Out-Null
    Set-Content -Path $MarkFile -Value $CurSha
}

# ChatGPT へのログイン
$loginOk = $true
try { codex login status | Out-Null } catch { $loginOk = $false }
if (-not $loginOk) {
    Info ""
    Info "▶ 初回ログイン: ChatGPT アカウントと接続します"
    Info "  ブラウザが開きます。ChatGPT (Plus/Pro/Business) でサインインしてください。"
    Info ""
    codex login
}

# 形状生成エンジン（TripoSR）の案内
if (-not (Test-Path (Join-Path $InstallDir "engine\TripoSR"))) {
    Info ""
    Info "▶ 3D 形状生成エンジン（TripoSR・無料）は初回利用時に別途セットアップします:"
    Info "  cd `"$InstallDir`" ; npm run setup-engine"
    Info "  （エンジンは macOS 向けが中心です。詳細は README を参照してください）"
}

OK ""
OK "✓ 起動します。ブラウザが自動で開きます。終了は Ctrl+C。"
OK ""
node bin\cli.js
