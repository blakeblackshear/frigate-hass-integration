#!/bin/bash

set -euo pipefail

# Add LOCAL_WORKSPACE_FOLDER to .env file
readonly wanted_line_key="LOCAL_WORKSPACE_FOLDER"
readonly wanted_line="${wanted_line_key}='${PWD}'"
readonly file=".env"
echo "Writing ${wanted_line} to ${file}" >&2
if [[ -f "${file}" ]] && grep -q "^${wanted_line_key}=" "${file}"; then
    sed -i "s,^${wanted_line_key}=.*,${wanted_line}," "${file}"
else
    echo "${wanted_line}" >>"${file}"
fi

# Ensure there is no leftover from previous run
docker compose down --remove-orphans --volumes

echo "$0 finished." >&2
