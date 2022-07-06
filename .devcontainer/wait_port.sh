#!/bin/bash

# Taken from https://stackoverflow.com/a/48646792/12156188

set -euo pipefail

echo -n "Waiting for Home Assistant Debugger to launch on 5678" >&2

while ! timeout 1 bash -c "echo > /dev/tcp/hass/5678" &>/dev/null; do
  sleep 1
  echo -n "." >&2
done
echo

echo "Home Assistant Debugger launched" >&2
