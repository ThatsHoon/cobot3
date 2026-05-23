#!/usr/bin/env bash
# scene_pull.sh — Google Drive 에서 scene 에셋 다운로드 후 압축해제
#
# 사전 조건: COBOT3_SCENE_GDRIVE_ID 환경변수 (공유 파일의 Google Drive File ID)
#
# Google Drive File ID 얻는 법:
#   공유 링크 https://drive.google.com/file/d/<FILE_ID>/view 에서 <FILE_ID> 부분
#
# 사용법:
#   export COBOT3_SCENE_GDRIVE_ID=1aBcDefGhIjKlMnOpQrStUvWxYz
#   bash main_side/scripts/scene_pull.sh
set -e

GDRIVE_FILE_ID="${COBOT3_SCENE_GDRIVE_ID:-}"

if [ -z "$GDRIVE_FILE_ID" ]; then
    echo "[scene_pull] 오류: COBOT3_SCENE_GDRIVE_ID 가 설정되지 않았습니다."
    echo "  export COBOT3_SCENE_GDRIVE_ID=<Google Drive File ID>"
    echo "  또는 ~/.bashrc 에 추가 후 다시 실행하세요."
    exit 1
fi

# gdown 설치 확인 (pip 경유 — Isaac python 외부 시스템 pip)
if ! command -v gdown &>/dev/null; then
    echo "[scene_pull] gdown 미설치 — pip install 중..."
    pip install -q gdown
fi

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
cd "$REPO_ROOT"

ARCHIVE="/tmp/cobot3_scene_assets.tar.gz"

echo "[scene_pull] 다운로드 중 (ID=$GDRIVE_FILE_ID) ..."
gdown "$GDRIVE_FILE_ID" -O "$ARCHIVE"

echo "[scene_pull] 압축 해제 중 ..."
tar -xzf "$ARCHIVE"
rm -f "$ARCHIVE"

echo "[scene_pull] 완료. main_side/scene/ 에셋 복원됨."
