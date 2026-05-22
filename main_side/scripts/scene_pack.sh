#!/usr/bin/env bash
# scene_pack.sh — main_side/scene/ 의 git-ignore 에셋만 압축
# 출력: 프로젝트 루트의 cobot3_scene_assets_YYYYMMDD.tar.gz
#
# 사용법:
#   bash main_side/scripts/scene_pack.sh
#   COBOT3_SCENE_ARCHIVE=/tmp/scene.tar.gz bash main_side/scripts/scene_pack.sh
set -e

REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
cd "$REPO_ROOT"

ARCHIVE="${COBOT3_SCENE_ARCHIVE:-cobot3_scene_assets_$(date +%Y%m%d).tar.gz}"

echo "[scene_pack] git-ignored 에셋 수집 중 ..."
# [1] main_side/scene/ — go2_policy/*/videos/ 는 학습 기록 영상(~151MB), 런타임 불필요 제외
# [2] sub1_side/server/models/*.pt — YOLO 커스텀 모델 (없으면 yolov8n 폴백으로 탐지 정확도 저하)
FILELIST=$(
  git ls-files --ignored --exclude-standard --others main_side/scene/ \
      | grep -v "go2_policy/.*/videos/"
  git ls-files --ignored --exclude-standard --others sub1_side/server/models/ \
      | grep "\.pt$"
)

if [ -z "$FILELIST" ]; then
    echo "[scene_pack] 경고: ignore된 파일이 없습니다 — 아카이브를 만들 필요가 없습니다."
    exit 0
fi

COUNT=$(echo "$FILELIST" | wc -l)
echo "[scene_pack] $COUNT 개 파일 → $ARCHIVE (go2_policy/videos/ 제외)"
echo "$FILELIST" | tar -czf "$ARCHIVE" -T -

SIZE=$(du -sh "$ARCHIVE" | cut -f1)
echo "[scene_pack] 완료: $ARCHIVE ($SIZE)"
echo ""
echo "구글 드라이브 업로드 후 FILE_ID 를 환경변수에 등록:"
echo "  export COBOT3_SCENE_GDRIVE_ID=<file_id>"
echo "또는 ~/.bashrc 에 추가 후 scene_pull.sh 실행."
