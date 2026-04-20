FROM mcr.microsoft.com/playwright/python:v1.58.0-noble

# Add uv to PATH early
ENV PATH="/root/.local/bin:${PATH}"

# Install uv and ripgrep
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && apt-get update && apt-get install -y --no-install-recommends ripgrep \
    && rm -rf /var/lib/apt/lists/*

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