#!/bin/bash
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

OS="$(uname -s)"

echo -e "${GREEN}Installing nkd-agents...${NC}"

# ── ripgrep ────────────────────────────────────────────────────────────────────
if ! command -v rg &>/dev/null; then
  echo -e "${YELLOW}Installing ripgrep...${NC}"
  if [[ "$OS" == "Darwin" ]]; then
    if ! command -v brew &>/dev/null; then
      echo -e "${YELLOW}Installing Homebrew...${NC}"
      /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    brew install ripgrep
  elif [[ "$OS" == "Linux" ]]; then
    if command -v apt-get &>/dev/null; then
      sudo apt-get update -qq && sudo apt-get install -y ripgrep
    elif command -v dnf &>/dev/null; then
      sudo dnf install -y ripgrep
    elif command -v pacman &>/dev/null; then
      sudo pacman -S --noconfirm ripgrep
    else
      echo -e "${RED}Could not install ripgrep — install it manually: https://github.com/BurntSushi/ripgrep${NC}"
    fi
  else
    echo -e "${RED}Unsupported OS: $OS — install ripgrep manually: https://github.com/BurntSushi/ripgrep${NC}"
  fi
else
  echo -e "${GREEN}✓ ripgrep already installed${NC}"
fi

# ── uv ────────────────────────────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
  echo -e "${YELLOW}Installing uv...${NC}"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
else
  echo -e "${GREEN}✓ uv already installed${NC}"
fi

# ── nkd CLI ───────────────────────────────────────────────────────────────────
echo -e "${YELLOW}Installing nkd CLI...${NC}"
uv tool install --force 'git+https://github.com/amitejmehta/nkd-agents.git[cli]'

# ── .env / API key ────────────────────────────────────────────────────────────
mkdir -p ~/.nkd-agents
if [ ! -f ~/.nkd-agents/.env ]; then
  echo -e "${YELLOW}Enter your Anthropic API key:${NC}"
  read -r api_key </dev/tty
  echo "ANTHROPIC_API_KEY=$api_key" > ~/.nkd-agents/.env
  echo -e "${GREEN}✓ API key saved to ~/.nkd-agents/.env${NC}"
else
  echo -e "${GREEN}✓ ~/.nkd-agents/.env already exists${NC}"
fi

# ── shell rc ──────────────────────────────────────────────────────────────────
SHELL_RC="$HOME/.zshrc"
[[ "$SHELL" == *"bash"* ]] && SHELL_RC="$HOME/.bashrc"

add_alias() {
  local name="$1" body="$2"
  if grep -q "alias ${name}=" "$SHELL_RC" 2>/dev/null; then
    # Overwrite existing alias line
    sed -i '' "s|^alias ${name}=.*|alias ${name}=\"${body}\"|" "$SHELL_RC"
    echo -e "${GREEN}✓ ${name} alias updated in $SHELL_RC${NC}"
  else
    echo "alias ${name}=\"${body}\"" >> "$SHELL_RC"
    echo -e "${GREEN}✓ ${name} alias added to $SHELL_RC${NC}"
  fi
}

if ! grep -q "# nkd-agents" "$SHELL_RC" 2>/dev/null; then
  echo "" >> "$SHELL_RC"
  echo "# nkd-agents" >> "$SHELL_RC"
fi

add_alias "nkd-update" "curl -fsSL https://raw.githubusercontent.com/amitejmehta/nkd-agents/main/install.sh | bash"

# ── Docker sandbox (nkd-sandbox) ──────────────────────────────────────────────
if command -v docker &>/dev/null; then
  # Open Docker Desktop if not already running (macOS)
  if ! docker info &>/dev/null 2>&1; then
    echo -e "${YELLOW}Starting Docker...${NC}"
    open -a Docker 2>/dev/null || true
    for i in $(seq 1 15); do
      docker info &>/dev/null 2>&1 && break
      sleep 2
    done
  fi
fi
if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
  echo -e "${YELLOW}Docker detected — pulling nkd-agents image...${NC}"
  docker pull ghcr.io/amitejmehta/nkd-agents:latest 2>/dev/null \
    || docker build -t nkd-agents 'https://github.com/amitejmehta/nkd-agents.git' \
    && docker tag nkd-agents ghcr.io/amitejmehta/nkd-agents:latest 2>/dev/null || true

  add_alias "nkd-sandbox" \
    "docker run -it --rm --env-file ~/.nkd-agents/.env -v \$(pwd):/workspace ghcr.io/amitejmehta/nkd-agents:latest"

  echo -e "${GREEN}✓ nkd-sandbox available — runs nkd inside a Docker container with cwd mounted${NC}"
else
  echo -e "${YELLOW}Docker not found or not running — skipping nkd-sandbox setup${NC}"
  echo -e "${YELLOW}  Install Docker and re-run this script to get nkd-sandbox${NC}"
fi

echo ""
echo -e "${GREEN}Done! Run: source $SHELL_RC && nkd${NC}"
