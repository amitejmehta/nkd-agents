FROM mcr.microsoft.com/playwright/python:v1.58.0-noble

# Add uv to PATH early
ENV PATH="/root/.local/bin:${PATH}"

ARG TARGETARCH

# Install uv, ripgrep, and gh via prebuilt binaries (avoids apt GPG issues)
RUN set -eux; \
    curl -LsSf https://astral.sh/uv/install.sh | sh; \
    case "${TARGETARCH:-$(dpkg --print-architecture)}" in \
        amd64) RG_ARCH=x86_64-unknown-linux-musl; GH_ARCH=linux_amd64 ;; \
        arm64) RG_ARCH=aarch64-unknown-linux-gnu; GH_ARCH=linux_arm64 ;; \
        *) echo "unsupported arch"; exit 1 ;; \
    esac; \
    RG_VER=14.1.1; \
    curl -fsSL "https://github.com/BurntSushi/ripgrep/releases/download/${RG_VER}/ripgrep-${RG_VER}-${RG_ARCH}.tar.gz" \
        | tar -xz -C /tmp; \
    mv "/tmp/ripgrep-${RG_VER}-${RG_ARCH}/rg" /usr/local/bin/rg; \
    chmod +x /usr/local/bin/rg; \
    GH_VER=2.60.1; \
    curl -fsSL "https://github.com/cli/cli/releases/download/v${GH_VER}/gh_${GH_VER}_${GH_ARCH}.tar.gz" \
        | tar -xz -C /tmp; \
    mv "/tmp/gh_${GH_VER}_${GH_ARCH}/bin/gh" /usr/local/bin/gh; \
    chmod +x /usr/local/bin/gh; \
    rm -rf /tmp/ripgrep-* /tmp/gh_*

# Copy only the package files needed for installation
COPY pyproject.toml /tmp/
COPY nkd_agents/ /tmp/nkd_agents/

# Install the package using uv with CLI and web dependencies
WORKDIR /tmp
RUN uv pip install --system ".[cli,web]"

# Create workspace directory and switch to non-root user
RUN mkdir -p /workspace && chown pwuser:pwuser /workspace
USER pwuser
WORKDIR /workspace

# Default command
CMD ["nkd"]
