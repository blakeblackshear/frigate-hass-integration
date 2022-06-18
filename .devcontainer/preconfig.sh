#!/bin/bash
# -----------------------------------------------------------------------------
# Preconfigure the Home Assistant container.
# -----------------------------------------------------------------------------
# This script is run before Home Assistant is started, through the S6-Overlay
# cont-init.d hook.
#
# This script must be mounted at /etc/cont-init.d/preconfig.sh:ro
#
# This script copies everything from every folder you mount in /preconfig.d/ to
# /config/ at the first Home Assistant initialization.
#
# It also ensures that the password for the users is set to their matching
# values in .storage/auth_provider.homeassistant.
#
# To re-run this script, you have to remove the Home Assistant container and
# create another.

set -euo pipefail

readonly markfile="/config/.preconfigured"
readonly source_dirs="/preconfig.d"
readonly target_dir="/config"

if [[ -f "${markfile}" ]]; then
    echo "Preconfigured already" >&2
    exit 0
fi

if [[ ! -d "${target_dir}" ]]; then
    echo "Target directory ${target_dir} does not exist" >&2
    exit 1
fi

echo "Preconfiguring..." >&2

for source in "${source_dirs}"/*; do
    if [[ ! -d "${source}" ]]; then
        echo "Skipping non-directory '${source}'" >&2
        continue
    fi
    echo "Copying files from '${source}' to '${target_dir}'" >&2
    cp --recursive --force --verbose "${source}/." "${target_dir}/"
done

readonly password_file="${target_dir}/.storage/auth_provider.homeassistant"
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
