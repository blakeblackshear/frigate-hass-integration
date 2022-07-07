#!/bin/bash

set -euxo pipefail

poetry install

poetry run pre-commit install
