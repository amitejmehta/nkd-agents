#!/bin/bash
set -e

GREEN='\033[0;32m'
WHITE='\033[1;37m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${WHITE}Installing nkd...${NC}"

# ── uv ────────────────────────────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
echo -e "${GREEN}✓${NC}${WHITE} uv${NC}"

# ── nkd CLI ───────────────────────────────────────────────────────────────────
uv tool install --force 'git+https://github.com/amitejmehta/nkd.git[web]'
echo -e "${GREEN}✓${NC}${WHITE} nkd${NC}"

# ── .env / API key ────────────────────────────────────────────────────────────
mkdir -p ~/.claude/nkd
ENV_FILE=~/.claude/nkd/.env
for key_name in ANTHROPIC_API_KEY OPENAI_API_KEY; do
  grep -qs "^${key_name}=" "$ENV_FILE" && continue
  echo -e "${WHITE}Enter your $key_name (Enter to skip):${NC}"
  read -rs api_key </dev/tty
  echo
  [ -z "$api_key" ] || (umask 077; printf '\n%s=%s\n' "$key_name" "$api_key" >> "$ENV_FILE")
done
echo -e "${GREEN}✓${NC}${WHITE} API keys${NC}"

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

if ! grep -q "# nkd" "$SHELL_RC" 2>/dev/null; then
  echo "" >> "$SHELL_RC"
  echo "# nkd" >> "$SHELL_RC"
fi

add_alias "nkdo" "NKD_PROVIDER=openai nkd"
add_alias "nkd-install" "curl -fsSL https://raw.githubusercontent.com/amitejmehta/nkd/main/install.sh | bash"

CYAN='\033[0;36m'
echo ""
echo -e "${WHITE}commands:${NC}"
echo -e "  ${CYAN}nkd${NC}${WHITE}          start the agent with anthropic${NC}"
echo -e "  ${CYAN}nkdo${NC}${WHITE}         start the agent with openai${NC}"
echo -e "  ${CYAN}nkd-install${NC}${WHITE}  install the agent${NC}"
echo ""
YELLOW='\033[1;33m'
echo -e "${WHITE}run: ${YELLOW}source $SHELL_RC && nkd${NC}"