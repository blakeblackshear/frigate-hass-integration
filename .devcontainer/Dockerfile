# syntax=docker/dockerfile:1.2

FROM mcr.microsoft.com/vscode/devcontainers/python:0-3.10

# Install Docker
ENV DOCKER_BUILDKIT="1"
# https://github.com/microsoft/vscode-dev-containers/commits/main/script-library/docker-debian.sh
ARG DOCKER_SCRIPT_VERSION="364972b0d7d20ee5de40c1084e65f3f1bc6d5951"
RUN bash -c "$(curl -fsSL "https://raw.githubusercontent.com/microsoft/vscode-dev-containers/${DOCKER_SCRIPT_VERSION}/script-library/docker-debian.sh")" \
    && rm -rf /var/lib/apt/lists/*
ENTRYPOINT ["/usr/local/share/docker-init.sh"]
CMD ["sleep", "infinity"]
