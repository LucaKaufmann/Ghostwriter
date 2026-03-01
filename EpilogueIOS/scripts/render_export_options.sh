#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IOS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TEMPLATE_PATH="${IOS_DIR}/ExportOptions-AppStore.plist"
OUTPUT_PATH="${1:-${IOS_DIR}/build/ExportOptions-AppStore.generated.plist}"

: "${EPILOGUE_IOS_DEVELOPMENT_TEAM:?Set EPILOGUE_IOS_DEVELOPMENT_TEAM}"
: "${EPILOGUE_IOS_APPSTORE_PROFILE:?Set EPILOGUE_IOS_APPSTORE_PROFILE}"

mkdir -p "$(dirname "${OUTPUT_PATH}")"
cp "${TEMPLATE_PATH}" "${OUTPUT_PATH}"

/usr/libexec/PlistBuddy -c "Set :teamID ${EPILOGUE_IOS_DEVELOPMENT_TEAM}" "${OUTPUT_PATH}"
/usr/libexec/PlistBuddy -c "Set :provisioningProfiles:com.codable.epilogue ${EPILOGUE_IOS_APPSTORE_PROFILE}" "${OUTPUT_PATH}"

echo "Generated ${OUTPUT_PATH}"
