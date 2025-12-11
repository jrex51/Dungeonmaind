<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useSessionStore } from '@/stores/session.ts'
import { useRecorderStore } from '@/stores/recorder.ts'
import { SERVER_CONFIG } from '@/config/config.ts'
import ConfigView from '@/views/ConfigView.vue'
import RulebookView from '@/views/RulebookView.vue'

/** Holds Header and session saving */

const router = useRouter()
const store = useSessionStore()
const recorder = useRecorderStore()

const showNameModal = ref(false)
const sessionName = ref("")
const showConfigModal = ref(false)
const showRulebookModal = ref(false)

/** Session actions */
async function onExport() {
  if (recorder.isRecording || recorder.isStopping || (recorder.recordedAudioURL && !recorder.canExportSession)) {
    alert("Please wait for recording and transcription to finish before saving the session.")
    return }


  if (!sessionName.value.trim()) return alert("Please enter a session name.")
  showNameModal.value = false
  console.log(sessionName.value)

  const res = await fetch(`${SERVER_CONFIG.BASE_URL}${SERVER_CONFIG.ENDPOINTS.EXPORT_SESSION}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_name: sessionName.value,
    }),
  })
}
</script>

<template>
  <div class="header">
    <div class="header-left"></div>
    <h1>Dungeonmaind</h1>
    <div class="header-right">
      <button class="rulebook-button" @click="showRulebookModal = true">Rulebook</button>
      <button v-if="store.isLeader" class="config-button" @click="showConfigModal = true">Config</button>
      <button
        v-if="store.isLeader"
        class="export-button"
        @click="showNameModal = true"
        :disabled="recorder.isRecording || recorder.isStopping || (!!recorder.recordedAudioURL && !recorder.canExportSession)"
      >
        Save Session
      </button>
    </div>
    <div v-if="showNameModal" class="modal-overlay">
      <div class="modal">
        <h2>Name your session</h2>
        <input
          v-model="sessionName"
          placeholder="Enter session name"
          class="modal-input"
        />
        <div class="modal-buttons">
          <button class="btn-cancel" @click="showNameModal = false">Cancel</button>
          <button class="btn-save" @click="onExport">Save</button>
        </div>
      </div>
    </div>
    <div v-if="showConfigModal" class="modal-overlay">
      <ConfigView @submit-success="showConfigModal = false" />
    </div>
    <div v-if="showRulebookModal" class="modal-overlay">
      <RulebookView @submit-success="showRulebookModal = false" />
    </div>
  </div>
</template>

<style src="@/assets/styles.css"></style>
<style scoped>
/* Header */
.header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 50px;
  background-color: rgba(160, 122, 57, 0.95);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 1rem;
  box-sizing: border-box;
  color: #e0d5b7;
  z-index: 1000;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.rulebook-button,
.config-button,
.export-button {
  padding: 0.5rem 1rem;
  background-color: rgba(53, 73, 94, 0.9);
  border: 1px solid #4a575e;
  border-radius: 4px;
  color: #fff;
  cursor: pointer;
  font-family: 'MedievalSharp', cursive;
  font-weight: normal;
  transition: background-color 0.3s ease;
}

.rulebook-button:hover,
.config-button:hover,
.export-button:hover {
  background-color: #4a575e;
}

.rulebook-button:disabled,
.config-button:disabled,
.export-button:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 9999;
}

.modal {
  background: rgba(163, 148, 95, 0.8);
  border-radius: 12px;
  padding: 24px;
  width: 320px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
  text-align: center;
}

.modal h2 {
  font-size: 1.2rem;
  font-weight: 600;
  margin-bottom: 1rem;
  font-family: 'MedievalSharp', cursive;
}

.modal-input {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid #ccc;
  border-radius: 6px;
  font-size: 1rem;
  font-family: 'MedievalSharp', cursive;
  font-weight: bolder;
  margin-bottom: 1rem;
  outline: none;
}

.modal-input:focus {
  border-color: #3b82f6;
  background-color: #f1e6b4;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.3);
}

.modal-buttons {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.btn-cancel,
.btn-save {
  padding: 6px 12px;
  border-radius: 6px;
  border: none;
  cursor: pointer;
  font-family: 'MedievalSharp', cursive;
  font-weight: 500;
  transition: background 0.2s ease;
}

.btn-cancel {
  background: #ddd;
}

.btn-cancel:hover {
  background: #ccc;
}

.btn-save {
  background: #2563eb;
  color: white;
}

.btn-save:hover {
  background: #1d4ed8;
}
</style>
