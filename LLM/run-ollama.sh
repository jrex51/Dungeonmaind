#!/usr/bin/env bash

ollama serve &
sleep 10
echo "Listing existing models..."
ollama list
# mistralai 3b model is choosen as default
ollama pull hf.co/bartowski/mistralai_Ministral-3-3B-Instruct-2512-GGUF:Q5_K_M
ollama pull hf.co/bartowski/microsoft_Phi-4-mini-instruct-GGUF:Q5_K_M
# If all models should be available on Docker pull also:
# ollama pull hf.co/bartowski/mistralai_Ministral-3-14B-Instruct-2512-GGUF:Q5_K_M
# ollama pull "hf.co/bartowski/google_gemma-3-1b-it-qat-GGUF:Q5_K_M",
# ollama pull "hf.co/bartowski/google_gemma-3-12b-it-qat-GGUF:Q5_K_M",


echo "Listing models after pull..."
ollama list