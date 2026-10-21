FROM docker.io/library/node:22-bookworm-slim

ARG CODEX_VERSION=0.162.1
ARG DEV_UID=1000
ARG DEV_GID=1000

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       bash ca-certificates curl gh git less openssh-client \
       python3 python3-venv ripgrep tmux \
    && rm -rf /var/lib/apt/lists/* \
    && npm install --global "@openai/codex@${CODEX_VERSION}" \
    && npm cache clean --force

LABEL local.codex.version="${CODEX_VERSION}"

# Match the SSH user's identity so bind-mounted project files retain ownership.
# Root callers use the existing root account; normal callers use node.
RUN if [ "$DEV_UID" != 0 ]; then \
        groupmod --gid "$DEV_GID" node \
        && usermod --uid "$DEV_UID" --gid "$DEV_GID" node; \
    fi \
    && mkdir -p /workspace /home/node/.codex \
    && chown -R "$DEV_UID:$DEV_GID" /home/node /workspace

ENV HOME=/home/node
ENV CODEX_HOME=/home/node/.codex
WORKDIR /workspace
USER ${DEV_UID}:${DEV_GID}
CMD ["sleep", "infinity"]
