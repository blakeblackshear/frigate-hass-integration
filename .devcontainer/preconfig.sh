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

readonly password_file="${source_dir}/.storage/auth_provider.homeassistant"
if [[ -f "${password_file}" ]]; then
    readarray -t users < <(jq --raw-output --compact-output '.data.users[].username' "${password_file}")
    for user in "${users[@]}"; do
        echo "Setting password for user '${user}" >&2
        password=$(jq --exit-status --raw-output --arg u "${user}" '.data.users[] | select(.username==$u) | .password' "${password_file}")
        hass --script auth --config /config change_password "${user}" "${password}"
    done
fi

touch "${markfile}"

echo "Preconfigured successfully" >&2
