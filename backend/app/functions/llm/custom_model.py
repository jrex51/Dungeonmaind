import ollama
import requests
import os
import json

# In case of local development (not with docker), it may be necessary to change here ollama with localhost.
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")

def run_custom_model(chat_history: list[dict]) -> str:
    """
    Sends a chat history to the Ollama model and returns the assistant's reply.
    """
    try:
        payload = {
            "model": "hf.co/bartowski/microsoft_Phi-4-mini-instruct-GGUF:Q5_K_M",
            "messages": chat_history,
            "stream": False
        }

        #print("Sending payload:", json.dumps(payload, indent=2))

        response = requests.post(f"{OLLAMA_URL}/api/chat", json=payload)
        response.raise_for_status()

        result = response.json()
        #print("Ollama response JSON:", result)

        return result.get("message", {}).get("content", "[No content in response]")
    except requests.exceptions.RequestException as e:
        print("Ollama call failed:", e)
        return "[Ollama API error]"
    except Exception as e:
        print("Unexpected error:", e)
        return "[Unexpected backend error]"