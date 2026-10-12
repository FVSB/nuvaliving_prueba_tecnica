FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

COPY apt-packages.txt /tmp/dev-apt-packages.txt
# The base ships an obsolete Yarn apt key; Yarn is not a project dependency.
RUN rm -f /etc/apt/sources.list.d/yarn.list \
    && apt-get update \
    && xargs -a /tmp/dev-apt-packages.txt apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-tools.txt /tmp/dev-requirements-tools.txt
RUN python -m pip install --no-cache-dir -r /tmp/dev-requirements-tools.txt
