#!/bin/bash
set -e

GREEN='\033[0;32m'
WHITE='\033[1;37m'
RED='\033[0;31m'
NC='\033[0m'

OS="$(uname -s)"

echo -e "${WHITE}Installing nkd-agents...${NC}"

# ── ripgrep ────────────────────────────────────────────────────────────────────
if ! command -v rg &>/dev/null; then
  echo -e "${WHITE}Installing ripgrep...${NC}"
  if [[ "$OS" == "Darwin" ]]; then
    if ! command -v brew &>/dev/null; then
      echo -e "${WHITE}Installing Homebrew...${NC}"
      /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    brew install ripgrep
  elif [[ "$OS" == "Linux" ]]; then
    if command -v apt-get &>/dev/null; then
      sudo apt-get update && sudo apt-get install -y ripgrep
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
fi
echo -e "${GREEN}✓${NC}${WHITE} ripgrep${NC}"

# ── uv ────────────────────────────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
echo -e "${GREEN}✓${NC}${WHITE} uv${NC}"

# ── nkd CLI ───────────────────────────────────────────────────────────────────
uv tool install --force 'git+https://github.com/amitejmehta/nkd-agents.git[cli,web]'
echo -e "${GREEN}✓${NC}${WHITE} nkd${NC}"

# ── skills ────────────────────────────────────────────────────────────────────
SKILLS_DEST="$HOME/.nkd-agents/skills"
mkdir -p "$SKILLS_DEST"
curl -sL https://github.com/amitejmehta/nkd-agents/archive/refs/heads/main.tar.gz \
  | tar -xz --strip-components=2 -C "$SKILLS_DEST" "nkd-agents-main/skills"
echo -e "${GREEN}✓${NC}${WHITE} skills${NC}"

# ── .env / API key ────────────────────────────────────────────────────────────
mkdir -p ~/.nkd-agents
if [ ! -f ~/.nkd-agents/.env ]; then
  echo -e "${WHITE}Enter your Anthropic API key:${NC}"
  read -r api_key </dev/tty
  echo "ANTHROPIC_API_KEY=$api_key" > ~/.nkd-agents/.env
  echo -e "${GREEN}✓${NC}${WHITE} API key saved${NC}"
else
  echo -e "${GREEN}✓${NC}${WHITE} ~/.nkd-agents/.env${NC}"
fi

# ── shell rc ──────────────────────────────────────────────────────────────────
SHELL_RC="$HOME/.zshrc"
[[ "$SHELL" == *"bash"* ]] && SHELL_RC="$HOME/.bashrc"

add_alias() {
  local name="$1" body="$2"
  if grep -q "alias ${name}=" "$SHELL_RC" 2>/dev/null; then
    grep -v "^alias ${name}=" "$SHELL_RC" > "${SHELL_RC}.tmp" && mv "${SHELL_RC}.tmp" "$SHELL_RC"
  fi
  echo "alias ${name}=\"${body}\"" >> "$SHELL_RC"
}

if ! grep -q "# nkd-agents" "$SHELL_RC" 2>/dev/null; then
  echo "" >> "$SHELL_RC"
  echo "# nkd-agents" >> "$SHELL_RC"
fi

add_alias "nkd-update" "curl -fsSL https://raw.githubusercontent.com/amitejmehta/nkd-agents/main/install.sh | bash"

# ── Docker sandbox (nkd-sandbox) ──────────────────────────────────────────────
if command -v docker &>/dev/null; then
  if ! docker info &>/dev/null 2>&1; then
    open -a Docker 2>/dev/null || true
    for i in $(seq 1 15); do
      docker info &>/dev/null 2>&1 && break
      sleep 2
    done
  fi
fi
if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
  docker pull ghcr.io/amitejmehta/nkd-agents:latest \
    || docker build -t nkd-agents 'https://github.com/amitejmehta/nkd-agents.git' \
    && docker tag nkd-agents ghcr.io/amitejmehta/nkd-agents:latest || true
  add_alias "nkd-sandbox" \
    "docker run -it --rm --env-file ~/.nkd-agents/.env -v \$(pwd):/workspace -v \$HOME/.nkd-agents:/home/pwuser/.nkd-agents ghcr.io/amitejmehta/nkd-agents:latest"
  echo -e "${GREEN}✓${NC}${WHITE} nkd-sandbox${NC}"
fi

CYAN='\033[0;36m'
echo ""
echo -e "${WHITE}commands:${NC}"
echo -e "  ${CYAN}nkd${NC}${WHITE}          start the agent${NC}"
echo -e "  ${CYAN}nkd-update${NC}${WHITE}   pull latest version${NC}"
echo -e "  ${CYAN}nkd-sandbox${NC}${WHITE}  run inside Docker with cwd mounted${NC}"
echo ""
YELLOW='\033[1;33m'
echo -e "${WHITE}run: ${YELLOW}source $SHELL_RC && nkd${NC}"