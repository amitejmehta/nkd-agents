#!/bin/bash
set -e

GREEN='\033[0;32m'
WHITE='\033[1;37m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${WHITE}Installing nkd-agents...${NC}"

# ── uv ────────────────────────────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
echo -e "${GREEN}✓${NC}${WHITE} uv${NC}"

# ── nkd CLI ───────────────────────────────────────────────────────────────────
uv tool install --force 'git+https://github.com/amitejmehta/nkd-agents.git[web]'
echo -e "${GREEN}✓${NC}${WHITE} nkd${NC}"

# ── .env / API key ────────────────────────────────────────────────────────────
mkdir -p ~/.claude/nkd
if [ ! -f ~/.claude/nkd/.env ]; then
  echo -e "${WHITE}Enter your Anthropic API key:${NC}"
  read -r api_key </dev/tty
  echo "ANTHROPIC_API_KEY=$api_key" > ~/.claude/nkd/.env
  echo -e "${GREEN}✓${NC}${WHITE} API key saved${NC}"
else
  echo -e "${GREEN}✓${NC}${WHITE} ~/.claude/nkd/.env${NC}"
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

add_alias "nkd-install" "curl -fsSL https://raw.githubusercontent.com/amitejmehta/nkd-agents/main/install.sh | bash"

CYAN='\033[0;36m'
echo ""
echo -e "${WHITE}commands:${NC}"
echo -e "  ${CYAN}nkd${NC}${WHITE}          start the agent${NC}"
echo -e "  ${CYAN}nkd-install${NC}${WHITE}  install the agent${NC}"
echo ""
YELLOW='\033[1;33m'
echo -e "${WHITE}run: ${YELLOW}source $SHELL_RC && nkd${NC}"