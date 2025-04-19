FROM mcr.microsoft.com/devcontainers/python:1-3.13

COPY --from=ghcr.io/astral-sh/uv:0.6 /uv /usr/local/bin/

RUN --mount=type=bind,source=requirements_dev.txt,target=/tmp/requirements_dev.txt \
    --mount=type=bind,source=requirements.txt,target=/tmp/requirements.txt \
    uv pip install -r /tmp/requirements_dev.txt --system

CMD ["sleep", "infinity"]
