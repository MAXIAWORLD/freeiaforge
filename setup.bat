@echo off
setlocal enabledelayedexpansion
title FreeIA Gateway — Setup Wizard

echo.
echo ============================================================
echo   FreeIA Gateway — Setup Wizard
echo   One-command setup: paste your free API keys below
echo ============================================================
echo.

REM ── Detect existing .env ──────────────────────────────────────
if exist "backend\.env" (
    echo [INFO] backend\.env already exists.
    set /p OVERWRITE=Overwrite it? [y/N]
    if /i not "!OVERWRITE!"=="y" (
        echo Keeping existing .env. Run: docker compose up --build
        pause
        exit /b 0
    )
)

REM ── Copy template ─────────────────────────────────────────────
if not exist "backend\.env.example" (
    echo [ERROR] backend\.env.example not found. Are you in the freeiaforge directory?
    pause
    exit /b 1
)
copy "backend\.env.example" "backend\.env" >nul
echo.

REM ── Provider list with signup links ──────────────────────────
echo Providers available (all free, no credit card):
echo.
echo  1. Cerebras   — https://cloud.cerebras.ai           (1M tokens/day)
echo  2. Groq        — https://console.groq.com/keys       (14 400 req/day)
echo  3. Sambanova   — https://cloud.sambanova.ai          (free tier)
echo  4. Gemini      — https://aistudio.google.com/apikey  (1 500 req/day + 1M ctx)
echo  5. HuggingFace — https://huggingface.co/settings/tokens
echo  6. Mistral     — https://console.mistral.ai/api-keys
echo  7. OpenRouter  — https://openrouter.ai/keys          (30+ free models)
echo  8. NVIDIA NIM  — https://build.nvidia.com            (40 RPM free)
echo.
echo You need at least ONE key. Press Enter to skip any provider.
echo.

REM ── Collect keys ─────────────────────────────────────────────
set /p CEREBRAS_KEY=Cerebras API key   :
set /p GROQ_KEY=Groq API key        :
set /p SAMBANOVA_KEY=Sambanova API key  :
set /p GEMINI_KEY=Gemini API key      :
set /p HF_KEY=HuggingFace API key  :
set /p MISTRAL_KEY=Mistral API key     :
set /p OPENROUTER_KEY=OpenRouter API key  :
set /p NVIDIA_KEY=NVIDIA NIM API key  :

REM ── Cloudflare (needs account ID too) ─────────────────────────
echo.
echo  9. Cloudflare Workers AI — https://dash.cloudflare.com (10 000 req/day)
echo     Requires Account ID + API Token (both needed, or skip)
set /p CF_ACCOUNT=Cloudflare Account ID  :
set /p CF_TOKEN=Cloudflare API Token   :

REM ── Detect Ollama ─────────────────────────────────────────────
echo.
echo Checking for local Ollama...
curl -s --max-time 2 http://localhost:11434 >nul 2>&1
if %errorlevel%==0 (
    echo [OK] Ollama detected at localhost:11434
    set OLLAMA_URL=http://localhost:11434
    set /p OLLAMA_MODEL=Ollama model to use [default: llama3.2]:
    if "!OLLAMA_MODEL!"=="" set OLLAMA_MODEL=llama3.2
) else (
    echo [--] Ollama not detected (install at https://ollama.ai to use local models)
    set OLLAMA_URL=http://localhost:11434
    set OLLAMA_MODEL=llama3.2
)

REM ── Optional: provider order ──────────────────────────────────
echo.
echo Provider priority order (comma-separated, press Enter for default):
echo Default: cerebras,groq,sambanova,gemini,huggingface,mistral,openrouter
set /p PROVIDER_ORDER=Custom order:

REM ── Write keys to .env ────────────────────────────────────────
echo.
echo Writing backend\.env ...

REM Use PowerShell to do a clean sed-style replacement
powershell -NoProfile -Command ^
  "$env = Get-Content 'backend\.env' -Raw;" ^
  "$env = $env -replace 'CEREBRAS_API_KEY=.*', 'CEREBRAS_API_KEY=%CEREBRAS_KEY%';" ^
  "$env = $env -replace 'GROQ_API_KEY=.*', 'GROQ_API_KEY=%GROQ_KEY%';" ^
  "$env = $env -replace 'SAMBANOVA_API_KEY=.*', 'SAMBANOVA_API_KEY=%SAMBANOVA_KEY%';" ^
  "$env = $env -replace 'GEMINI_API_KEY=.*', 'GEMINI_API_KEY=%GEMINI_KEY%';" ^
  "$env = $env -replace 'HUGGINGFACE_API_KEY=.*', 'HUGGINGFACE_API_KEY=%HF_KEY%';" ^
  "$env = $env -replace 'MISTRAL_API_KEY=.*', 'MISTRAL_API_KEY=%MISTRAL_KEY%';" ^
  "$env = $env -replace 'OPENROUTER_API_KEY=.*', 'OPENROUTER_API_KEY=%OPENROUTER_KEY%';" ^
  "$env = $env -replace 'NVIDIA_NIM_API_KEY=.*', 'NVIDIA_NIM_API_KEY=%NVIDIA_KEY%';" ^
  "$env = $env -replace 'CLOUDFLARE_ACCOUNT_ID=.*', 'CLOUDFLARE_ACCOUNT_ID=%CF_ACCOUNT%';" ^
  "$env = $env -replace 'CLOUDFLARE_API_TOKEN=.*', 'CLOUDFLARE_API_TOKEN=%CF_TOKEN%';" ^
  "$env = $env -replace 'OLLAMA_BASE_URL=.*', 'OLLAMA_BASE_URL=%OLLAMA_URL%';" ^
  "$env = $env -replace 'OLLAMA_MODEL=.*', 'OLLAMA_MODEL=%OLLAMA_MODEL%';" ^
  "if ('%PROVIDER_ORDER%' -ne '') { $env = $env -replace 'PROVIDER_ORDER=.*', 'PROVIDER_ORDER=%PROVIDER_ORDER%' };" ^
  "Set-Content 'backend\.env' $env -NoNewline"

echo [OK] backend\.env configured.

REM ── Count configured providers ────────────────────────────────
set CONFIGURED=0
if not "%CEREBRAS_KEY%"=="" set /a CONFIGURED+=1
if not "%GROQ_KEY%"=="" set /a CONFIGURED+=1
if not "%SAMBANOVA_KEY%"=="" set /a CONFIGURED+=1
if not "%GEMINI_KEY%"=="" set /a CONFIGURED+=1
if not "%HF_KEY%"=="" set /a CONFIGURED+=1
if not "%MISTRAL_KEY%"=="" set /a CONFIGURED+=1
if not "%OPENROUTER_KEY%"=="" set /a CONFIGURED+=1
if not "%NVIDIA_KEY%"=="" set /a CONFIGURED+=1
if not "%CF_TOKEN%"=="" set /a CONFIGURED+=1

echo.
echo ============================================================
echo  %CONFIGURED% provider(s) configured.
if %CONFIGURED%==0 (
    echo  [WARN] No keys entered. Gateway will start but all requests will fail.
    echo         Edit backend\.env and add at least one key, then run start.bat
)
echo ============================================================
echo.

set /p LAUNCH=Launch FreeIA Gateway now? [Y/n]
if /i "!LAUNCH!"=="n" (
    echo Run: start.bat  (or: docker compose up --build)
    pause
    exit /b 0
)

docker compose up --build
