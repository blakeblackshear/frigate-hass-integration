#!/usr/bin/with-contenv bashio
# ==============================================================================
# Start Home Assistant service
# This file was taken from:
# https://github.com/home-assistant/core/blob/dd6725b80a5efebda36c64c78250f3374e85c3a7/rootfs/etc/services.d/home-assistant/run
# And modified to allow starting the Python Debugger.
# ==============================================================================

# shellcheck shell=bash

cd /config || bashio::exit.nok "Can't find config folder!"

# Enable mimalloc for Home Assistant Core, unless disabled
if [[ -z "${DISABLE_JEMALLOC+x}" ]]; then
  export LD_PRELOAD="/usr/local/lib/libjemalloc.so.2"
  export MALLOC_CONF="background_thread:true,metadata_thp:auto,dirty_decay_ms:20000,muzzy_decay_ms:20000"
fi

debug_args=()
if bashio::var.true "${PYTHON_DEBUG:-"false"}"; then
  debug_args=(-m debugpy --listen 0.0.0.0:5678)
  bashio::log.info "Enabling Python debug server on port 5678"
fi

exec python3 "${debug_args[@]}" -m homeassistant --config /config
