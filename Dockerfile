FROM python:3.12-slim

ENV PATH="/root/.local/bin:${PATH}"

ARG TARGETARCH

RUN set -eux; \
    apt-get update && apt-get install -y --no-install-recommends \
        curl chromium ripgrep \
    && rm -rf /var/lib/apt/lists/*; \
    curl -LsSf https://astral.sh/uv/install.sh | sh; \
    case "${TARGETARCH:-$(dpkg --print-architecture)}" in \
        amd64) GH_ARCH=linux_amd64 ;; \
        arm64) GH_ARCH=linux_arm64 ;; \
        *) echo "unsupported arch"; exit 1 ;; \
    esac; \
    GH_VER=2.60.1; \
    curl -fsSL "https://github.com/cli/cli/releases/download/v${GH_VER}/gh_${GH_VER}_${GH_ARCH}.tar.gz" \
        | tar -xz -C /tmp; \
    mv "/tmp/gh_${GH_VER}_${GH_ARCH}/bin/gh" /usr/local/bin/gh; \
    chmod +x /usr/local/bin/gh; \
    rm -rf /tmp/gh_*

# Copy only the package files needed for installation
COPY pyproject.toml /tmp/
COPY nkd_agents/ /tmp/nkd_agents/

# Install the package using uv with CLI and web dependencies
WORKDIR /tmp
RUN uv pip install --system ".[cli,web]"

# Create workspace directory
RUN mkdir -p /workspace
WORKDIR /workspace

# Default command
CMD ["nkd"]
