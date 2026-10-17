#!/usr/bin/env bash
set -Eeuo pipefail

ready_file="${OLLAMA_READY_FILE:-/tmp/ollama-ready}"
rm -f "$ready_file"
ollama serve &
server_pid=$!

cleanup() {
    rm -f "$ready_file"
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

# Poll readiness instead of assuming a fixed startup duration.
server_ready=false
for attempt in {1..60}; do
    if ollama list >/dev/null 2>&1; then
        server_ready=true
        break
    fi
    if ! kill -0 "$server_pid" 2>/dev/null; then
        echo "Ollama server exited before becoming ready." >&2
        exit 1
    fi
    sleep 1
done
if [ "$server_ready" != true ]; then
    echo "Ollama did not become ready within 60 seconds." >&2
    exit 1
fi

# Keep the project's original model selection. Existing models are reused.
models=(
    "hf.co/bartowski/mistralai_Ministral-3-3B-Instruct-2512-GGUF:Q5_K_M"
    "hf.co/bartowski/microsoft_Phi-4-mini-instruct-GGUF:Q5_K_M"
)
for model in "${models[@]}"; do
    if ollama show "$model" >/dev/null 2>&1; then
        echo "Using saved model: $model"
    else
        echo "Downloading missing model: $model"
        ollama pull "$model"
    fi
done

touch "$ready_file"
echo "Ollama and required models are ready."
wait "$server_pid"
