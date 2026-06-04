#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/briefcase_build.sh <target> <app> [step]

Arguments:
  target  One of: macOS, windows, android, iOS
  app     One of: polaris_desktop, polaris_mobile
  step    Optional; one of: create, build, package, all (default: all)

Examples:
  scripts/briefcase_build.sh macOS polaris_desktop all
  scripts/briefcase_build.sh windows polaris_desktop package
  scripts/briefcase_build.sh android polaris_mobile all
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -lt 2 || $# -gt 3 ]]; then
  usage
  exit 1
fi

TARGET="$1"
APP="$2"
STEP="${3:-all}"

case "$TARGET" in
  macOS|windows|android|iOS) ;;
  *)
    echo "Invalid target: $TARGET"
    usage
    exit 1
    ;;
esac

case "$APP" in
  polaris_desktop|polaris_mobile) ;;
  *)
    echo "Invalid app: $APP"
    usage
    exit 1
    ;;
esac

case "$STEP" in
  create|build|package|all) ;;
  *)
    echo "Invalid step: $STEP"
    usage
    exit 1
    ;;
esac

run_step() {
  local cmd_step="$1"
  echo "==> briefcase ${cmd_step} ${TARGET} -a ${APP}"
  briefcase "${cmd_step}" "${TARGET}" -a "${APP}" --no-input
}

if [[ "$STEP" == "all" ]]; then
  run_step create
  run_step build
  run_step package
else
  run_step "$STEP"
fi

echo "Done."
