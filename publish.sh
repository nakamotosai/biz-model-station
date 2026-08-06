#!/usr/bin/env bash
# publish.sh — biz-research → GitHub 公开仓自动发布
# 由 collect.py 尾部调用（generate_site/generate_md 之后），把最新内容推到
# github.com/nakamotosai/biz-model-station（公开仓，deploy key: vps-native-publish）
#
# 原则：发布仓只含 data(无 bak)/markdown/scripts/README，天然排除 logs/pyc/drafts
#   —— 与生产仓（SSOT 全历史）刻意分离；这里用干净快照保证公开仓无审计痕迹。
set -euo pipefail

ROOT=/home/ubuntu/biz-research
PUB=/srv/biz-public
GIT_SSH=/home/ubuntu/.ssh/github-biz-pub

# 1. 同步干净内容（rsync 不可用则 cp + 清理）
rm -rf "$PUB/data" "$PUB/markdown" "$PUB/scripts"
mkdir -p "$PUB/data" "$PUB/markdown" "$PUB/scripts"

# data：排除 .bak / 隐藏状态 / _drafts
shopt -s nullglob
for f in "$ROOT"/data/*.json; do
  b=$(basename "$f")
  case "$b" in
    *.bak*|.collect*) continue ;;
  esac
  cp "$f" "$PUB/data/"
done
[ -f "$ROOT/data/SCHEMA.md" ] && cp "$ROOT/data/SCHEMA.md" "$PUB/data/"

# markdown：全部
cp "$ROOT"/markdown/*.md "$PUB/markdown/"

# scripts：排除 bak/pyc/probe/dbg
for f in "$ROOT"/scripts/*.py "$ROOT"/scripts/collect.py; do
  [ -e "$f" ] || continue
  b=$(basename "$f")
  case "$b" in
    *.bak*|probe*|*.pyc) continue ;;
  esac
  cp "$f" "$PUB/scripts/"
done

# README（若生产无则从公开仓拉一次）
if [ ! -f "$PUB/README.md" ]; then
  GIT_SSH_COMMAND="ssh -i $GIT_SSH -o IdentitiesOnly=yes -o BatchMode=yes" \
    git -C "$PUB" pull -q origin main 2>/dev/null || true
fi
[ -f "$ROOT/README.md" ] && cp "$ROOT/README.md" "$PUB/README.md"

# 2. commit + push
cd "$PUB"
git add -A
if git diff --cached --quiet; then
  echo "[publish] 无内容变更，跳过 push"
  exit 0
fi
git -c user.email=biz-publish@biz.saaaai.com -c user.name=biz-publish \
  commit -qm "sync: $(date '+%Y-%m-%d %H:%M') 自动发布"
GIT_SSH_COMMAND="ssh -i $GIT_SSH -o IdentitiesOnly=yes -o BatchMode=yes" \
  git push origin main -q
echo "[publish] 已推送到公开仓 main"
