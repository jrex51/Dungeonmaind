# Dungeon M-AI-nd

> Transcribe, search, and query your **Dungeons & Dragons** sessions – locally and private, with AI support.

**Dungeon M-AI-nd** is a locally running software solution for analyzing DnD campaigns. It records voice input, automatically transcribes it, stores the content in a searchable format, and allows you to ask questions about earlier events in your campaign – completely without cloud services.

---

## Project Goal

The goal ist to efficiently record you DnD sessions and to make them searchable. Players should be able to ask questions like:

- *"What happend to the magical dagger?"*
- *"What did the NPC say before we left the city?"*

and get accurate answers based on real transcriptions of their sessions.

---

## Features

### Implemented
- [x] Voice recording via the frontend (in progress)
- [x] Transcription using WhisperX
- [x] Integration of a local LLM for answering questions
- [x] Intuitive web interface (Vue + TypeScript) - partially implemented

### Planned
- [ ] Storage of transcribed texts in a database
- [ ] Campaign export and archiving functionality
- [ ] Offline mode for laptops/tablets at the game table
- [ ] Character, location and event tracking

---

## System Overview

🎙️ Recording → 🧠 Transcription (WhisperX) 
→ 🧩 Embedding → 💾 Storage → 🤖 Q&A via LLM

---

## Installation

### Requirements
- Python 3.12
- Git
- Node.js
- (optional but recommended) GPU with CUDA for accelerated transcription by WhisperX and answer-response times by the llm
- ffmpeg (for WhisperX) - very important!
  
### 1. Clone the repository
```text
git clone https://github.com/FNitzsche/Dungeonmaind.git
cd Dungeonmaind
```

### 2. Set up the Python environment
```text
pip install -r requirements.txt
```
For GPU support you need to install CUDA (CUDA Toolkit 12.8.1), cuDNN (cuDNN 9.10.2), ctranslate2 (4.6.0) and:
```text
pip uninstall torch torchaudio
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128
```



### 3. Initialize the frontend
See the README.md file in the 'frontend' folder (first run ```npm install```, then ```npm run dev```)

___

## 💬 Usage

### Record a Session
1. Start the Frontend-App (npm run dev – work in progress).
2. Click on "Start recording".
3. Audio is sent to the backend, transcribed and stored

### Ask questions
Use the web interface to ask questions like:
```text
"What happend in the tavern?"
```
The LLM will answer based on the stored transcriptions.


