#!/bin/bash

set -euo pipefail

readonly markfile="/config/.preconfigured"
readonly source_dir="/config/preconfig"
readonly target_dir="/config"

if [[ -f "${markfile}" ]]; then
    echo "Preconfigured already" >&2
    exit 0
fi

if [[ ! -d "${source_dir}" ]]; then
    echo "Preconfiguration directory '${source_dir}' does not exist" >&2
    exit 1
fi

if [[ ! -d "${target_dir}" ]]; then
    echo "Target directory ${target_dir} does not exist" >&2
    exit 1
fi

echo "Preconfiguring" >&2

cp --recursive --force --verbose "${source_dir}/." "${target_dir}/"

hass --script auth --config /config change_password "admin" "admin"

touch "${markfile}"

echo "Preconfigured successfully" >&2
