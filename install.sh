#!/bin/bash
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}Installing nkd-agents...${NC}"

# Install Homebrew if missing (macOS)
if ! command -v brew &>/dev/null; then
  echo -e "${YELLOW}Installing Homebrew...${NC}"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

# Install ripgrep
if ! command -v rg &>/dev/null; then
  echo -e "${YELLOW}Installing ripgrep...${NC}"
  brew install ripgrep
else
  echo -e "${GREEN}✓ ripgrep already installed${NC}"
fi

# Install uv
if ! command -v uv &>/dev/null; then
  echo -e "${YELLOW}Installing uv...${NC}"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
else
  echo -e "${GREEN}✓ uv already installed${NC}"
fi

# Install nkd-agents
echo -e "${YELLOW}Installing nkd CLI...${NC}"
uv tool install --force 'git+https://github.com/amitejmehta/nkd_agents.git[cli]'

# Set up .env
mkdir -p ~/.nkd-agents
if [ ! -f ~/.nkd-agents/.env ]; then
  echo -e "${YELLOW}Enter your Anthropic API key:${NC}"
  read -r api_key </dev/tty
  echo "ANTHROPIC_API_KEY=$api_key" > ~/.nkd-agents/.env
  echo -e "${GREEN}✓ API key saved to ~/.nkd-agents/.env${NC}"
else
  echo -e "${GREEN}✓ ~/.nkd-agents/.env already exists${NC}"
fi

# Add nkd-update alias
SHELL_RC="$HOME/.zshrc"
[[ "$SHELL" == *"bash"* ]] && SHELL_RC="$HOME/.bashrc"

if ! grep -q "nkd-update" "$SHELL_RC" 2>/dev/null; then
  echo "" >> "$SHELL_RC"
  echo "# nkd-agents" >> "$SHELL_RC"
  echo "alias nkd-update=\"uv tool install --force 'git+https://github.com/amitejmehta/nkd_agents.git[cli]'\"" >> "$SHELL_RC"
  echo -e "${GREEN}✓ nkd-update alias added to $SHELL_RC${NC}"
else
  echo -e "${GREEN}✓ nkd-update alias already set${NC}"
fi

echo ""
echo -e "${GREEN}Done! Run: source $SHELL_RC && nkd${NC}"
