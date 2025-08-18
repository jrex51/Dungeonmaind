<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { SERVER_CONFIG, LLM_OPTIONS, DEFAULT_LLM, TRANSCRIPTION_MODELS, DEFAULT_TRANSCRIPTION_MODEL } from '@/config/config'

const router = useRouter()
const LLM_STORAGE_KEY = 'selectedLLM'
const TRANSCRIPTION_STORAGE_KEY = 'transcriptionModel'
const selectedLLM = ref(localStorage.getItem(LLM_STORAGE_KEY) || DEFAULT_LLM)
const selectedTranscriptionModel = ref(localStorage.getItem(TRANSCRIPTION_STORAGE_KEY) || DEFAULT_TRANSCRIPTION_MODEL)
const clearChat = ref(false)

watch(selectedLLM, (newVal) => {
  localStorage.setItem(LLM_STORAGE_KEY, newVal)
})

watch(selectedTranscriptionModel, (newVal) => {
  localStorage.setItem('transcriptionModel', newVal)
})

function goHome() {
  router.push('/')
}

async function submitSelection() {
  goHome()
  try {
    const response = await fetch(`${SERVER_CONFIG.BASE_URL}${SERVER_CONFIG.ENDPOINTS.CHANGE_CONFIG}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ selected_LLM: selectedLLM.value,
        transcription_model: selectedTranscriptionModel.value,
        clear_chat: clearChat.value })
    })

    if (!response.ok) {
      throw new Error(`Request failed with status ${response.status}`)
    }

    console.log('Configuration successfully submitted:', selectedLLM.value)
  } catch (error) {
    console.error('Error calling LLM endpoint:', error)
  }
}

</script>

<template>
  <div class="config-page">
    <h1>Configuration Page</h1>

    <label for="selection">Choose an LLM:</label>
    <select id="selection" v-model="selectedLLM">
      <option v-for="llm in LLM_OPTIONS" :key="llm.value" :value="llm.value">
        {{ llm.label }}
      </option>
    </select>

    <hr style="margin: 1rem 0" />

    <label for="transModel">Choose Transcription Model:</label>
    <select id="transModel" v-model="selectedTranscriptionModel">
      <option v-for="model in TRANSCRIPTION_MODELS" :key="model.value" :value="model.value">
        {{ model.label }}
      </option>
    </select>

    <hr style="margin: 1rem 0" />

    <label>
      <input type="checkbox" v-model="clearChat" />
      Clear Chat History
    </label>

    <hr style="margin: 1rem 0" />

    <button @click="submitSelection" class="done-button">Done</button>
  </div>
</template>

<style scoped>
.config-page {
  max-width: 600px;
  margin: 2rem auto;
  padding: 1rem;
  text-align: center;
}

select {
  margin-top: 1rem;
  padding: 0.5rem;
  font-size: 1rem;
}

.done-button {
  margin-top: 2rem;
  padding: 0.75rem 1.5rem;
  font-size: 1rem;
  background-color: #42b983;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.done-button:hover {
  background-color: #369f6e;
}
</style>
