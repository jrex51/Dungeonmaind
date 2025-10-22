import { defineStore } from 'pinia'
import {DEFAULT_LLM, DEFAULT_TRANSCRIPTION_MODEL, DEFAULT_EMBEDDING_MODEL, DEFAULT_EMBEDDING_TopK} from '@/config/config'

export const useConfigStore = defineStore('config', {
  state: () => ({
    selectedLLM: DEFAULT_LLM,
    transcriptionModel: DEFAULT_TRANSCRIPTION_MODEL,
    embeddingModel: DEFAULT_EMBEDDING_MODEL,
    embeddingTopK: DEFAULT_EMBEDDING_TopK
  }),
  actions: {
    setConfig(cfg: any) {
      this.selectedLLM = cfg.selected_LLM
      this.transcriptionModel = cfg.transcription_model
      this.embeddingModel = cfg.embedding_model
      this.embeddingTopK = cfg.embedding_top_k
    }
  }
})
