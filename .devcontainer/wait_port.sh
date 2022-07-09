#!/bin/bash

# Taken from https://stackoverflow.com/a/48646792/12156188

set -euo pipefail

echo -n "Waiting for Home Assistant Debugger to launch on 5678" >&2

sleep 5
echo

echo "Home Assistant Debugger launched" >&2
