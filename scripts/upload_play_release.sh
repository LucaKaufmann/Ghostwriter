#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/upload_play_release.sh --version-code <int> [options]

Options:
  --version-code <int>        Android versionCode (required, must increase each upload)
  --version-name <string>     Android versionName (default: 1.0.0)
  --track <name>              Play track: internal|alpha|beta|production (default: internal)
  --play-credentials <path>   Path to Google Play service account JSON
                              (default: $HOME/.config/epilogue/play-service-account.json)
  --skip-checks               Skip :app:test and :app:lintRelease before upload
  -h, --help                  Show this help
EOF
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION_CODE="${EPILOGUE_VERSION_CODE:-}"
VERSION_NAME="${EPILOGUE_VERSION_NAME:-1.0.0}"
PLAY_TRACK="${EPILOGUE_PLAY_TRACK:-internal}"
PLAY_CREDENTIALS="${EPILOGUE_PLAY_CREDENTIALS:-$HOME/.config/epilogue/play-service-account.json}"
SKIP_CHECKS="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version-code)
      VERSION_CODE="${2:-}"
      shift 2
      ;;
    --version-name)
      VERSION_NAME="${2:-}"
      shift 2
      ;;
    --track)
      PLAY_TRACK="${2:-}"
      shift 2
      ;;
    --play-credentials)
      PLAY_CREDENTIALS="${2:-}"
      shift 2
      ;;
    --skip-checks)
      SKIP_CHECKS="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$VERSION_CODE" ]]; then
  echo "Missing required --version-code." >&2
  usage
  exit 1
fi

if ! [[ "$VERSION_CODE" =~ ^[0-9]+$ ]]; then
  echo "versionCode must be an integer: $VERSION_CODE" >&2
  exit 1
fi

case "$PLAY_TRACK" in
  internal|alpha|beta|production) ;;
  *)
    echo "Invalid --track '$PLAY_TRACK'. Use internal|alpha|beta|production." >&2
    exit 1
    ;;
esac

if [[ ! -f "$ROOT_DIR/keystore.properties" ]]; then
  echo "Missing $ROOT_DIR/keystore.properties (see keystore.properties.example)." >&2
  exit 1
fi

if [[ ! -f "$PLAY_CREDENTIALS" ]]; then
  echo "Play service account JSON not found: $PLAY_CREDENTIALS" >&2
  exit 1
fi

if [[ "$SKIP_CHECKS" != "true" ]]; then
  echo "Running pre-upload checks (:app:test :app:lintRelease)..."
  (cd "$ROOT_DIR" && ./gradlew :app:test :app:lintRelease)
fi

echo "Publishing release bundle to Google Play ($PLAY_TRACK track)..."
(
  cd "$ROOT_DIR"
  EPILOGUE_VERSION_CODE="$VERSION_CODE" \
  EPILOGUE_VERSION_NAME="$VERSION_NAME" \
  EPILOGUE_PLAY_TRACK="$PLAY_TRACK" \
  EPILOGUE_PLAY_CREDENTIALS="$PLAY_CREDENTIALS" \
  ./gradlew :app:publishReleaseBundle
)

echo "Upload completed."
