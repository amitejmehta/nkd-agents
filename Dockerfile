FROM mcr.microsoft.com/playwright/python:v1.58.0-noble

# Add uv to PATH early
ENV PATH="/root/.local/bin:${PATH}"

# Install uv, ripgrep, and gh (GitHub CLI)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && mkdir -p -m 755 /etc/apt/keyrings \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends ripgrep gh \
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