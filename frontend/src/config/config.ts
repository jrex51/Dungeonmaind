import { useSessionStore } from '@/stores/session.ts'
// Set the server and enpdoints
export const SERVER_CONFIG = {
  get BASE_URL() {
    const store = useSessionStore();
    return store.backendUrl || "http://localhost:8000"; // Fallback
  },
  get LOCAL_NETWORK_IP() {
    const store = useSessionStore();
    return store.localNetworkIP || "localhost"; // Fallback
  },
  ENDPOINTS: {
    RUN_LLM: '/llm/run',
    TRANSCRIBE_AUDIO_FILE: '/processAudioData/transcribeAudioFile',
    CHANGE_CONFIG: '/config/changeConfig',
    GET_CONFIG: '/config/getConfig',
    CHECK_CONNECTION: '/health/checkConnection',
    WS_PLAYERS: '/ws/players',
    RULEBOOK_FOLDERS: '/rulebook/folders',
    RULEBOOK_FILE: '/rulebook/file',
    RULEBOOK_SEARCH: '/rulebook/search',
  },
}

// Set the available LLM models
export const LLM_OPTIONS = [
  { value: 'hf.co/bartowski/microsoft_Phi-4-mini-instruct-GGUF:Q5_K_M', label: 'Phi4-3.8B' },
  { value: 'hf.co/bartowski/Qwen_Qwen3-1.7B-GGUF:Q5_K_M', label: 'Qwen3-1.7B' },
  { value: 'hf.co/bartowski/google_gemma-3-1b-it-qat-GGUF:Q5_K_M', label: 'Gemma3-1B' },
  { value: 'hf.co/bartowski/google_gemma-3-12b-it-qat-GGUF:Q5_K_M', label: 'Gemma3-12B' },
]

// Set the default LLM model
export const DEFAULT_LLM = LLM_OPTIONS[0].value

// Set the available transcription models
export const TRANSCRIPTION_MODELS = [
  { value: 'base', label: 'Base' },
  { value: 'medium', label: 'Medium' },
  { value: 'large-v3', label: 'Large' },
]

// Set the default transcription model
export const DEFAULT_TRANSCRIPTION_MODEL = TRANSCRIPTION_MODELS[0].value

// Set the available embedding models
export const EMBEDDING_MODELS = [
  { value: 'all-MiniLM-L6-v2', label: 'all-MiniLM-L6-v2' },
  { value: 'all-MiniLM-L12-v2', label: 'all-MiniLM-L12-v2' },
  { value: 'paraphrase-multilingual-MiniLM-L12-v2', label: 'paraphrase-multilingual-MiniLM-L12-v2' },
]

// Set the default embedding model
export const DEFAULT_EMBEDDING_MODEL = EMBEDDING_MODELS[0].value

// Set the available embedding models
export const EMBEDDING_TopK = [
  { value: '1', label: '1' },
  { value: '2', label: '2' },
  { value: '3', label: '3' },
  { value: '4', label: '4' },
]

// Set the default embedding model
export const DEFAULT_EMBEDDING_TopK = EMBEDDING_MODELS[1].value
