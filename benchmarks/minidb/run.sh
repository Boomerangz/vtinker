#!/bin/bash
# minidb benchmark runner
# Usage: ./run.sh <workdir> [plan_model] [execute_model] [review_model]
#
# Examples:
#   ./run.sh /tmp/bench-minidb openrouter/deepseek-v3.2
#   ./run.sh /tmp/bench-minidb openrouter/deepseek-v3.2 openrouter/qwen3-coder-next openrouter/deepseek-v3.2

set -e

WORKDIR="${1:?Usage: $0 <workdir> [plan_model] [execute_model] [review_model]}"
PLAN_MODEL="${2:-openrouter/deepseek-v3.2}"
EXECUTE_MODEL="${3:-$PLAN_MODEL}"
REVIEW_MODEL="${4:-$PLAN_MODEL}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== minidb benchmark ==="
echo "Workdir:  $WORKDIR"
echo "Plan:     $PLAN_MODEL"
echo "Execute:  $EXECUTE_MODEL"
echo "Review:   $REVIEW_MODEL"
echo ""

# Setup
rm -rf "$WORKDIR"
mkdir -p "$WORKDIR/.vtinker" "$WORKDIR/apps/minidb"
cd "$WORKDIR" && git init

# Copy and patch epic
cp "$SCRIPT_DIR/epic.md" "$WORKDIR/epic.md"
sed -i.bak "s|{workdir}|$WORKDIR|g" "$WORKDIR/epic.md" && rm -f "$WORKDIR/epic.md.bak"

# Create config
sed \
  -e "s|{workdir}|$WORKDIR|g" \
  -e "s|<PLAN_MODEL>|$PLAN_MODEL|g" \
  -e "s|<EXECUTE_MODEL>|$EXECUTE_MODEL|g" \
  -e "s|<REVIEW_MODEL>|$REVIEW_MODEL|g" \
  "$SCRIPT_DIR/config.json" > "$WORKDIR/.vtinker/config.json"

echo "Starting vtinker..."
vtinker start --from "$WORKDIR/epic.md" --dir "$WORKDIR" 2>&1 | tee "$WORKDIR/output.log"
