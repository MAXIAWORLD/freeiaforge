#!/bin/sh
set -e

banner() {
    echo ""
    echo "============================================================"
    echo "  FreeIA Gateway — Setup Wizard"
    echo "  One-command setup: paste your free API keys below"
    echo "============================================================"
    echo ""
}

ask() {
    printf "%s" "$1"
    IFS= read -r REPLY
    echo "$REPLY"
}

replace_env() {
    KEY="$1"
    VAL="$2"
    # portable sed: works on macOS + Linux
    if [ "$(uname)" = "Darwin" ]; then
        sed -i "" "s|^${KEY}=.*|${KEY}=${VAL}|" backend/.env
    else
        sed -i "s|^${KEY}=.*|${KEY}=${VAL}|" backend/.env
    fi
}

# ── Guard ───────────────────────────────────────────────────────
if [ ! -f backend/.env.example ]; then
    echo "[ERROR] backend/.env.example not found. Run this from the freeiaforge/ directory."
    exit 1
fi

banner

# ── Existing .env check ──────────────────────────────────────────
if [ -f backend/.env ]; then
    echo "[INFO] backend/.env already exists."
    OVERWRITE=$(ask "Overwrite it? [y/N] ")
    if [ "$OVERWRITE" != "y" ] && [ "$OVERWRITE" != "Y" ]; then
        echo "Keeping existing .env. Run: docker compose up --build"
        exit 0
    fi
fi

cp backend/.env.example backend/.env

# ── Provider list with signup links ──────────────────────────────
echo "Providers available (all free, no credit card):"
echo ""
echo "  1. Cerebras   — https://cloud.cerebras.ai           (1M tokens/day)"
echo "  2. Groq        — https://console.groq.com/keys       (14 400 req/day)"
echo "  3. Sambanova   — https://cloud.sambanova.ai          (free tier)"
echo "  4. Gemini      — https://aistudio.google.com/apikey  (1 500 req/day + 1M ctx)"
echo "  5. HuggingFace — https://huggingface.co/settings/tokens"
echo "  6. Mistral     — https://console.mistral.ai/api-keys"
echo "  7. OpenRouter  — https://openrouter.ai/keys          (30+ free models)"
echo "  8. NVIDIA NIM  — https://build.nvidia.com            (40 RPM free)"
echo ""
echo "You need at least ONE key. Press Enter to skip any provider."
echo ""

# ── Collect keys ─────────────────────────────────────────────────
CEREBRAS_KEY=$(ask "Cerebras API key   : ")
GROQ_KEY=$(ask "Groq API key        : ")
SAMBANOVA_KEY=$(ask "Sambanova API key  : ")
GEMINI_KEY=$(ask "Gemini API key      : ")
HF_KEY=$(ask "HuggingFace API key  : ")
MISTRAL_KEY=$(ask "Mistral API key     : ")
OPENROUTER_KEY=$(ask "OpenRouter API key  : ")
NVIDIA_KEY=$(ask "NVIDIA NIM API key  : ")

echo ""
echo "  9. Cloudflare Workers AI — https://dash.cloudflare.com (10 000 req/day)"
echo "     Requires Account ID + API Token (both needed, or skip)"
CF_ACCOUNT=$(ask "Cloudflare Account ID  : ")
CF_TOKEN=$(ask "Cloudflare API Token   : ")

# ── Detect Ollama ─────────────────────────────────────────────────
echo ""
echo "Checking for local Ollama..."
if curl -s --max-time 2 http://localhost:11434 >/dev/null 2>&1; then
    echo "[OK] Ollama detected at localhost:11434"
    OLLAMA_URL="http://localhost:11434"
    OLLAMA_MODEL=$(ask "Ollama model to use [default: llama3.2]: ")
    [ -z "$OLLAMA_MODEL" ] && OLLAMA_MODEL="llama3.2"
else
    echo "[--] Ollama not detected (install at https://ollama.ai)"
    OLLAMA_URL="http://localhost:11434"
    OLLAMA_MODEL="llama3.2"
fi

# ── Optional provider order ───────────────────────────────────────
echo ""
echo "Provider priority order (comma-separated, Enter for default):"
echo "Default: cerebras,groq,sambanova,gemini,huggingface,mistral,openrouter"
PROVIDER_ORDER=$(ask "Custom order: ")

# ── Write .env ────────────────────────────────────────────────────
echo ""
echo "Writing backend/.env ..."

replace_env "CEREBRAS_API_KEY"     "$CEREBRAS_KEY"
replace_env "GROQ_API_KEY"         "$GROQ_KEY"
replace_env "SAMBANOVA_API_KEY"    "$SAMBANOVA_KEY"
replace_env "GEMINI_API_KEY"       "$GEMINI_KEY"
replace_env "HUGGINGFACE_API_KEY"  "$HF_KEY"
replace_env "MISTRAL_API_KEY"      "$MISTRAL_KEY"
replace_env "OPENROUTER_API_KEY"   "$OPENROUTER_KEY"
replace_env "NVIDIA_NIM_API_KEY"   "$NVIDIA_KEY"
replace_env "CLOUDFLARE_ACCOUNT_ID" "$CF_ACCOUNT"
replace_env "CLOUDFLARE_API_TOKEN"  "$CF_TOKEN"
replace_env "OLLAMA_BASE_URL"      "$OLLAMA_URL"
replace_env "OLLAMA_MODEL"         "$OLLAMA_MODEL"
[ -n "$PROVIDER_ORDER" ] && replace_env "PROVIDER_ORDER" "$PROVIDER_ORDER"

echo "[OK] backend/.env configured."

# ── Count configured providers ────────────────────────────────────
CONFIGURED=0
[ -n "$CEREBRAS_KEY"   ] && CONFIGURED=$((CONFIGURED+1))
[ -n "$GROQ_KEY"       ] && CONFIGURED=$((CONFIGURED+1))
[ -n "$SAMBANOVA_KEY"  ] && CONFIGURED=$((CONFIGURED+1))
[ -n "$GEMINI_KEY"     ] && CONFIGURED=$((CONFIGURED+1))
[ -n "$HF_KEY"         ] && CONFIGURED=$((CONFIGURED+1))
[ -n "$MISTRAL_KEY"    ] && CONFIGURED=$((CONFIGURED+1))
[ -n "$OPENROUTER_KEY" ] && CONFIGURED=$((CONFIGURED+1))
[ -n "$NVIDIA_KEY"     ] && CONFIGURED=$((CONFIGURED+1))
[ -n "$CF_TOKEN"       ] && CONFIGURED=$((CONFIGURED+1))

echo ""
echo "============================================================"
echo "  $CONFIGURED provider(s) configured."
if [ "$CONFIGURED" -eq 0 ]; then
    echo "  [WARN] No keys entered. Edit backend/.env then run start.sh"
fi
echo "============================================================"
echo ""

LAUNCH=$(ask "Launch FreeIA Gateway now? [Y/n] ")
if [ "$LAUNCH" = "n" ] || [ "$LAUNCH" = "N" ]; then
    echo "Run: ./start.sh  (or: docker compose up --build)"
    exit 0
fi

docker compose up --build
