# Local Models

How to run local LLMs on this machine and connect them to nkd-agents.

## Hardware

- **Machine:** Apple Silicon Mac, 36 GB unified RAM
- **GPU:** Apple Metal (integrated; shares RAM with CPU — no discrete VRAM)
- **Implication:** All model weights live in unified RAM. 36 GB limits which models fit.

## Model Recommendations

| Model | Quantisation | RAM | Fits? | Notes |
|---|---|---|---|---|
| Qwen2.5-32B-Instruct | Q4 (4-bit) | ~18–20 GB | ✅ comfortably | Recommended default |
| Qwen2.5-72B-Instruct | Q4 (4-bit) | ~36 GB | ⚠️ tight | Close all other apps; use AWQ checkpoint |
| Qwen2.5-72B-Instruct | BF16 | ~144 GB | ❌ | Won't fit |

**Recommended default:** `Qwen2.5-32B-Instruct` at Q4.

---

## vllm-metal

[`vllm-metal`](https://github.com/vllm-project/vllm-metal) is the official vLLM plugin for Apple Silicon. It uses MLX as the compute backend and exposes the full vLLM API surface — including the **Responses API** (`/v1/responses`) that nkd-agents uses natively. No proxy or adapter needed.

Standard `pip install vllm` does not support Apple Silicon GPU. Use vllm-metal.

### Install

```bash
curl -fsSL https://raw.githubusercontent.com/vllm-project/vllm-metal/main/install.sh | bash
source ~/.venv-vllm-metal/bin/activate
```

To reinstall cleanly: `rm -rf ~/.venv-vllm-metal` then re-run the above.

### Launch

```bash
source ~/.venv-vllm-metal/bin/activate

vllm serve Qwen/Qwen2.5-32B-Instruct \
  --enable-auto-tool-choice \
  --tool-call-parser hermes \
  --port 8000
```

For 72B (requires AWQ checkpoint — standard HF repo is BF16 and won't fit):

```bash
vllm serve Qwen/Qwen2.5-72B-Instruct-AWQ \
  --enable-auto-tool-choice \
  --tool-call-parser hermes \
  --port 8000
```

**Tool calling flags:**
- `--enable-auto-tool-choice` — model decides when to call tools
- `--tool-call-parser hermes` — Qwen models use Hermes token format

### Verify

```bash
curl http://localhost:8000/v1/models
```

---

## Connecting nkd-agents

### `.env` config

```bash
OPENAI_BASE_URL=http://localhost:8000/v1
OPENAI_API_KEY=empty
```

### How it works

`nkd_agents/openai.py` will construct the client as:

```python
client = AsyncOpenAI(
    base_url=os.environ.get("OPENAI_BASE_URL"),
    api_key=os.environ.get("OPENAI_API_KEY", "empty"),
)
```

`client.responses.create(...)` routes to the local model. Tools, conversation history — everything works identically to the cloud API.

> **Implementation status:** `OPENAI_BASE_URL` wiring lands in task OAI-2.

### Quick start

```bash
# 1. Start vllm-metal
source ~/.venv-vllm-metal/bin/activate
vllm serve Qwen/Qwen2.5-32B-Instruct --enable-auto-tool-choice --tool-call-parser hermes --port 8000

# 2. Set .env
echo 'OPENAI_BASE_URL=http://localhost:8000/v1' >> .env
echo 'OPENAI_API_KEY=empty' >> .env

# 3. Launch nkd (once OAI-2 + OAI-3 land)
nkd --provider openai
```
