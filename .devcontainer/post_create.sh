#!/bin/bash

set -euxo pipefail

uv pip install -r requirements_dev.txt --system

pre-commit install --install-hooks
