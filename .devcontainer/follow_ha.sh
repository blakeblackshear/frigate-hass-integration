#!/bin/bash

set -euo pipefail

# This ensures the container is up and, it
# won't do anything if it is already up.
docker compose up --detach hass

# Use docker logs instead of docker compose logs because the latter
# never exits, even after container is stopped.
container_id=$(docker compose ps hass --quiet)

# Only get the logs since the last time the container was started, so
# that we don't confuse VS Code's problem matcher.
start_time=$(docker inspect --format '{{.State.StartedAt}}' "${container_id}")

exec docker logs --follow "${container_id}" --since "${start_time}"
