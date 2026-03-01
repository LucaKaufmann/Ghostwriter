#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IOS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
WORKSPACE="${IOS_DIR}/Epilogue.xcworkspace"
SCHEME="Epilogue"
OUTPUT_ROOT="${EPILOGUE_SCREENSHOT_OUTPUT_ROOT:-${IOS_DIR}/artifacts/screenshots}"
FIXTURE_PATH="${EPILOGUE_SCREENSHOT_FIXTURE_PATH:-}"

DEFAULT_DEVICES=(
  "iPhone 16 Pro Max"
  "iPhone 16 Pro"
  "iPad Pro 13-inch (M4)"
)

if [[ $# -gt 0 ]]; then
  DEVICES=("$@")
else
  DEVICES=("${DEFAULT_DEVICES[@]}")
fi

if [[ ! -d "${WORKSPACE}" ]]; then
  echo "Workspace not found. Generating with Tuist..."
  (cd "${IOS_DIR}" && tuist generate --no-open)
fi

mkdir -p "${OUTPUT_ROOT}"

available_json="$(xcrun simctl list devices available --json)"

ran_any=0
for device in "${DEVICES[@]}"; do
  selected_runtime_and_udid="$(
    jq -r --arg name "${device}" '
      .devices
      | to_entries[]
      | .key as $runtime
      | .value[]
      | select(.name == $name and .isAvailable == true)
      | "\($runtime)|\(.udid)"
    ' <<<"${available_json}" | sort -r | head -n1
  )"

  if [[ -z "${selected_runtime_and_udid}" ]]; then
    echo "Skipping unavailable simulator: ${device}"
    continue
  fi

  runtime="${selected_runtime_and_udid%%|*}"
  udid="${selected_runtime_and_udid##*|}"

  slug="$(echo "${device}" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//')"
  device_output_dir="${OUTPUT_ROOT}/${slug}"
  rm -rf "${device_output_dir}"
  mkdir -p "${device_output_dir}"
  result_bundle="${device_output_dir}/result.xcresult"
  attachments_dir="${device_output_dir}/attachments"

  echo "Capturing screenshots on ${device} (${runtime}, ${udid})..."
  EPILOGUE_SCREENSHOT_OUTPUT_DIR="${device_output_dir}" \
  EPILOGUE_SCREENSHOT_FIXTURE_PATH="${FIXTURE_PATH}" \
  xcodebuild test \
    -workspace "${WORKSPACE}" \
    -scheme "${SCHEME}" \
    -destination "platform=iOS Simulator,id=${udid}" \
    -resultBundlePath "${result_bundle}" \
    -only-testing:EpilogueUITests/EpilogueScreenshotTests/testCaptureStoreScreenshots

  xcrun xcresulttool export attachments --path "${result_bundle}" --output-path "${attachments_dir}" >/dev/null

  while IFS= read -r row; do
    exported_name="$(jq -r '.exportedFileName' <<<"${row}")"
    suggested_name="$(jq -r '.suggestedHumanReadableName' <<<"${row}")"
    cleaned_name="$(echo "${suggested_name}" | sed -E 's/_[0-9]+_[A-F0-9-]+\.png$/.png/')"
    cp "${attachments_dir}/${exported_name}" "${device_output_dir}/${cleaned_name}"
  done < <(jq -c '.[]?.attachments[]?' "${attachments_dir}/manifest.json")

  echo "Saved screenshots to ${device_output_dir}"
  ran_any=1
done

if [[ ${ran_any} -eq 0 ]]; then
  echo "No screenshots captured because no requested simulators are available."
  exit 1
fi

echo "Done. Screenshot output root: ${OUTPUT_ROOT}"
