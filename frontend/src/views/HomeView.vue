<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useSessionStore } from '@/stores/session.ts'
import { useRouter } from 'vue-router'
import { SERVER_CONFIG } from '../config/config'

const router = useRouter()
const store = useSessionStore()

/** UI state */
const userInput = ref<string>('')
const modelOutput = ref<string>('')
const isLoading = ref<boolean>(false)
const askRulebook = ref<boolean>(false)
let socket: WebSocket | null = null

/** Audio (file upload) */
const selectedAudioFile = ref<File | null>(null)
const audioUploadStatus = ref<string>('')

/** Audio (recording) */
const micPermissionStatus = ref('')
const isRecording = ref(false)
const audioStream = ref<MediaStream | null> (null)
const mediaRecorder = ref<MediaRecorder | null >(null)
const audioChunks = ref<Blob[]>([])
const recordedAudioURL = ref<string | null>(null)
const currentAudio = ref<HTMLAudioElement | null>(null)

/** Dice */
const diceResult = ref<string>('')

/** Ability PATCH*/
const abilityBusy = ref<Record<string, boolean>>({})

function apiBase(): string {
  return store.backendUrl ?? SERVER_CONFIG.BASE_URL
}

/** Navigation */
function goToConfig() {
  router.push('/config')
}

/** Build WS URL from HTTP base + path */
function wsUrl(baseHttpUrl: string, path: string): string {
  const u = new URL(baseHttpUrl)
  u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:'
  u.pathname = path.startsWith('/') ? path : `/${path}`
  return u.toString()
}

/** Session actions */
async function onLeave() {
  await store.leave()
  router.push({ name: 'login' })
}

/** WebSocket lifecycle */
onMounted(() => {
  socket = new WebSocket(wsUrl(apiBase(), SERVER_CONFIG.ENDPOINTS.WS_PLAYERS))

  socket.onopen = async () => {
    try {
      await store.loadPlayers() // initial list
    } catch (e) {
      console.error('loadPlayers failed', e)
    }
  }

  socket.onmessage = (ev) => {
    const msg = JSON.parse(ev.data)
    if (msg.type === 'join') {
      // de-duplicate
      store.applyWsJoin(msg.player)
    } else if (msg.type === 'leave') {
      store.applyWsLeave(msg.player_id)
    } else if (msg.type === 'update' && msg.player?.id) {
      // upsert minimal update handler
      store.applyWsUpdate(msg.player)
    }
  }
})

onUnmounted(() => {
  try { socket?.close() } catch {}
  llmAbort.value?.abort()
  audioStream.value?.getTracks().forEach(t => t.stop())
  if (recordedAudioURL.value) URL.revokeObjectURL(recordedAudioURL.value)
})

/** LLM streaming with abort */
const llmAbort = ref<AbortController | null>(null)

async function handleLLMQuestionSubmit() {
  if (isLoading.value) return // prevent spamming the button
  isLoading.value = true
  modelOutput.value = ''
  llmAbort.value?.abort() // cancel any previous request
  llmAbort.value = new AbortController()

  try {
    const response = await fetch(
      `${apiBase()}${SERVER_CONFIG.ENDPOINTS.RUN_LLM}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          player_id: store.currentPlayer?.id,
          input_string: userInput.value,
          use_rulebook: askRulebook.value
        }),
        signal: llmAbort.value.signal
      }
    )
    if (!response.ok || !response.body) throw new Error(`Request failed with status ${response.status}`)

    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const chunk = decoder.decode(value, { stream: true })
      modelOutput.value += chunk
    }
  } catch (error: any) {
    if (error?.name !== 'AbortError') {
      console.error('Error calling LLM endpoint:', error)
      modelOutput.value = 'Error calling model, error: ' + error
    }
  } finally {
    isLoading.value = false
  }
}

/** Audio upload */
async function handleAudioUpload() {
  if (!selectedAudioFile.value) {
    audioUploadStatus.value = 'Please choose an audio file.'
    return
  }

  const formData = new FormData()
  formData.append('audio', selectedAudioFile.value)

  try {
    const response = await fetch(`${SERVER_CONFIG.BASE_URL}${SERVER_CONFIG.ENDPOINTS.TRANSCRIBE_AUDIO_FILE}`, {
      method: 'POST',
      body: formData,
    })
    if (!response.ok) {
      throw new Error(`Upload failed with status ${response.status}`)
    }
    const result = await response.json()
    audioUploadStatus.value = `Upload successfull: ${result.message || 'Audio file received'}`
  } catch (error) {
    console.error('An error occured while uploading your audio file:', error)
    audioUploadStatus.value = 'Upload error'
  }
}

function onAudioFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  if (target?.files && target.files.length > 0) {
    selectedAudioFile.value = target.files[0]
  } else {
    selectedAudioFile.value = null
  }
}

async function startRecording(){
  try{
    const stream = await navigator.mediaDevices.getUserMedia({audio: true})
    micPermissionStatus.value = 'Microphone access granted.'
    audioStream.value = stream
    audioChunks.value = []
    recordedAudioURL.value = null

    mediaRecorder.value = new MediaRecorder(stream)
    mediaRecorder.value.ondataavailable = (e) => e.data.size && audioChunks.value.push(e.data)
    mediaRecorder.value.onstop = () => {
      const audioBlob = new Blob(audioChunks.value, {type: 'audio/wav'  })
      recordedAudioURL.value = URL.createObjectURL(audioBlob)
    }

    mediaRecorder.value.start()
    isRecording.value = true
  } catch(error){
    console.error('Microphone access denied:', error)
    micPermissionStatus.value = 'Microphone access required'
  }
}


function stopRecording(){
    mediaRecorder.value?.stop()
    isRecording.value = false
}


function playRecording(){
  if(!recordedAudioURL.value) return

  if(!currentAudio.value) {
    currentAudio.value = new Audio(recordedAudioURL.value)
  }

  currentAudio.value.pause()
  currentAudio.value.currentTime = 0
  currentAudio.value.play()

}

async function transcribeRecording() {
  if (!audioChunks.value.length){
    audioUploadStatus.value = 'No audio to transcribe !'
    return
  }

  const audioBlob = new Blob(audioChunks.value,{type: 'audio/wav'})
  const formData = new FormData()
  formData.append('audio', audioBlob, 'recording.wav')

  try {
    const response = await fetch(`${SERVER_CONFIG.BASE_URL}${SERVER_CONFIG.ENDPOINTS.TRANSCRIBE_AUDIO_FILE}`,{
      method: 'POST',
      body: formData
    })

    if (!response.ok){
      throw new Error(`Transcription failed with status ${response.status}`)
    }

    const result = await response.json()
    audioUploadStatus.value = `Transcription: ${result.message || 'Success'}`
  } catch (error) {
    console.error('Transcription error:', error)
    audioUploadStatus.value = 'Transcription failed.'
  }
}

/** Dice */
function rollDice(sides: number) {
  const result = Math.floor(Math.random() * sides) + 1
  diceResult.value = `W${sides} → ${result}`
}

/** Abilities */
type AbilitySpec = {
  key: 'str' | 'dex' | 'con' | 'int_' | 'wis' | 'cha'
  label: string
}
const ABILITIES: AbilitySpec[] = [
  { key: 'str', label: 'STR' },
  { key: 'dex', label: 'DEX' },
  { key: 'con', label: 'CON' },
  { key: 'int_', label: 'INT' },
  { key: 'wis', label: 'WIS' },
  { key: 'cha', label: 'CHA' },
]

function getAbilityData(p: any) {
  const abil = p?.abilities ?? {}
  return ABILITIES.map(spec => {
    const score = typeof abil[spec.key] === 'number' ? abil[spec.key] : undefined
    const mod = score !== undefined ? Math.floor((score - 10) / 2) : undefined
    return { ...spec, score, mod }
  })
}

/** Ability change */
async function patchAbility(playerId: string, key: AbilitySpec['key'], value: number) {
  if (!playerId) return
  abilityBusy.value[key] = true
  try {
    const res = await fetch(`${apiBase()}/players/${playerId}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'X-Player-Id': playerId, // Self-permission header expected by backend
      },
      body: JSON.stringify({ [key]: value }),
    })
    if (!res.ok) {
      const msg = await res.text().catch(() => res.statusText)
      throw new Error(msg || `HTTP ${res.status}`)
    }
    // No local mutation — we rely on WS "update" to refresh the UI.
  } catch (e) {
    console.error('Ability PATCH failed:', e)
  } finally {
    abilityBusy.value[key] = false
  }
}

function incAbility(p: any, key: AbilitySpec['key']) {
  const current = Number(p?.abilities?.[key] ?? 0)
  patchAbility(p.id, key, current + 1)
}
function decAbility(p: any, key: AbilitySpec['key']) {
  const current = Number(p?.abilities?.[key] ?? 0)
  patchAbility(p.id, key, current - 1)
}

/** Visible players (for abilities): leader sees members (not self/other leaders); member sees self */
const visiblePlayers = computed(() => {
  const players = store.players ?? []
  if (store.isLeader) {
    const selfId = store.currentPlayer?.id
    return players.filter((p: any) => {
      const isSelf = selfId != null && p?.id === selfId
      const role = typeof p?.role === 'string' ? p.role.toLowerCase() : ''
      const isLeaderRole = role === 'leader'
      return !isSelf && !isLeaderRole
    })
  }
  return store.currentPlayer ? [store.currentPlayer] : []
})
</script>

<template>
  <div class="container">
    <div class="header">
      <div class="header-left"></div>
      <h1>Dungeonmaind</h1>
      <button class="config-button" @click="goToConfig">Config</button>
    </div>

    <div class="centered-content">
      <section>
        <h2>Hello {{ store.currentPlayer?.name }}</h2>
        <p v-if="store.isLeader">You are Leader.</p>
        <button @click="onLeave">Leave</button>

        <!-- Only leaders see the full player list -->
        <h3 v-if="store.isLeader">Spieler</h3>
        <ul v-if="store.isLeader">
          <li v-for="p in store.players" :key="p.id">
            {{ p.name }} ({{ p.role }})
          </li>
        </ul>
      </section>

      <div class="content-section">
        <h2>Ask Something about the DnD-Session</h2>
        <input
          v-model="userInput"
          type="text"
          placeholder="Type something..."
          class="input-field"
          @keyup.enter="handleLLMQuestionSubmit"
        />
        <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
          <input type="checkbox" v-model="askRulebook" />
          Ask rulebook
        </label>
        <button @click="handleLLMQuestionSubmit" class="submit-button" :disabled="isLoading">
          {{ isLoading ? 'Loading...' : 'Submit' }}
        </button>
        <div v-if="modelOutput" class="output">
          <h3>Model Output:</h3>
          <pre style="white-space: pre-wrap; margin: 0">{{ modelOutput }}</pre>
        </div>
      </div>

      <hr style="margin: 2rem 0" />

      <!-- Leader-only: recording -->
      <div v-if="store.isLeader" class="content-section">
        <h2>Record Using Microphone</h2>
        <button @click="startRecording" v-if="!isRecording" class="submit-button">Start Recording</button>
        <button @click="stopRecording" v-if="isRecording" class="submit-button">Stop Recording</button>

        <div v-if="isRecording" class="output">
          <p>Recording in progress</p>
        </div>
        <div v-if="micPermissionStatus" class="output">
          <p>{{ micPermissionStatus }}</p>
        </div>
        <div v-if="recordedAudioURL" class="output">
          <p>Recording completed</p>
        </div>

        <div v-if="recordedAudioURL" class="play-button">
          <button @click="playRecording" class="submit-button">Play Recording</button>
          <button @click="transcribeRecording" class="submit-button">Transcribe Recording</button>
        </div>
      </div>

      <hr style="margin: 2rem 0" />

      <!-- Leader-only: upload -->
      <div v-if="store.isLeader" class="content-section">
        <h2>Upload Audio File</h2>
        <input type="file" accept="audio/*" @change="onAudioFileChange" class="input-field" />
        <button @click="handleAudioUpload" class="submit-button">Upload Audio</button>
        <div v-if="audioUploadStatus" class="output">
          <p>{{ audioUploadStatus }}</p>
        </div>
      </div>

      <!-- Right rail: abilities & dice -->
      <aside class="right-rail">
        <section class="abilities-section rail-panel">
          <h2 v-if="!store.isLeader">Your ability scores</h2>
          <h2 v-else>Abilities of members</h2>

          <div v-if="visiblePlayers.length" class="ability-list">
            <div
              v-for="p in visiblePlayers"
              :key="p.id ?? p.name ?? JSON.stringify(p)"
              class="ability-card"
            >
              <div class="ability-card__header" v-if="store.isLeader">
                <strong>{{ p.name ?? 'Unbenannter Spieler' }}</strong>
                <span class="ability-card__role" v-if="p.role">({{ p.role }})</span>
              </div>

              <div class="ability-grid">
                <div v-for="a in getAbilityData(p)" :key="a.key" class="ability-box">
                  <div class="ability-label">{{ a.label }}</div>
                  <div class="ability-score">
                    <span>{{ a.score ?? '—' }}</span>
                  </div>

                  <!-- + / − controls: only for the current member (not leader) -->
                  <div
                    v-if="!store.isLeader && p.id === store.currentPlayer?.id"
                    class="ability-controls"
                  >
                    <button
                      class="ability-stepper"
                      :disabled="abilityBusy[a.key]"
                      @click="decAbility(p, a.key)"
                      aria-label="decrease"
                    >−</button>
                    <button
                      class="ability-stepper"
                      :disabled="abilityBusy[a.key]"
                      @click="incAbility(p, a.key)"
                      aria-label="increase"
                    >+</button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <p v-else class="output">No players found.</p>
        </section>

        <div class="dice-widget rail-panel">
          <div class="dice-buttons">
            <button @click="rollDice(4)" class="dice-button">W4</button>
            <button @click="rollDice(6)" class="dice-button">W6</button>
            <button @click="rollDice(8)" class="dice-button">W8</button>
            <button @click="rollDice(12)" class="dice-button">W12</button>
            <button @click="rollDice(20)" class="dice-button">W20</button>
          </div>
          <div class="dice-result" v-if="diceResult">{{ diceResult }}</div>
        </div>
      </aside>
    </div>
  </div>
</template>

<!-- This block essential for full-page background -->
<style>
html,
body {
  margin: 0;
  padding: 0;
  width: 100%;
  height: 100%;
  background-image: url('/bg-texture.jpg');
  background-size: cover;
  background-position: center;
  background-attachment: fixed;
  background-color: rgba(160, 122, 57, 0.95);
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}
</style>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=MedievalSharp&display=swap');

/* Left */
.container {
  max-width: 600px;
  margin: 2rem auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  max-height: 90vh;
}

.header {
  position: fixed; top: 0; left: 0; right: 0; height: 50px;
  background-color: rgba(160,122,57,0.95);
  display: flex; align-items: center; justify-content: center;
  padding: 0 1rem; box-sizing: border-box; color: #e0d5b7; z-index: 1000;
}

.centered-content {
  background-color: rgba(163,148,95,0.8);
  padding: 2rem; border-radius: 8px;
  max-width: 600px; width: 100%;
  box-sizing: border-box;
  border: 1px solid rgba(255,255,255,0.2);
  box-shadow: 0 4px 30px rgba(0,0,0,0.4);
  margin-top: 60px;
}

.config-button {
  position: absolute; right: 1rem;
  padding: 0.5rem 1rem;
  background-color: rgba(53,73,94,0.9);
  border: 1px solid #4a575e; border-radius: 4px;
  color: white; cursor: pointer;
  font-family: 'MedievalSharp', cursive;
  font-weight: normal;
  z-index: 1001;
  transition: background-color 0.3s ease;
}
.config-button:hover { background-color: #4a575e; }

.content-section { display: flex; flex-direction: column; align-items: center; }

h1 {
  color: #392401; text-align: center; padding-top: 20px;
  margin: 0 0 1.5rem; font-family: 'MedievalSharp', cursive; font-weight: bolder;
}

h2 {
  color: #392401; text-align: center; margin: 0 0 1.5rem;
  font-size: x-large; font-family: 'MedievalSharp', cursive; font-weight: bolder;
}

hr { width: 100%; border: none; border-top: 1px solid rgba(94,80,53,0.5); margin: 2rem 0; }

.input-field {
  padding: 0.75rem; font-size: 1rem; margin-bottom: 1rem;
  border: 1px solid #695710; border-radius: 10px;
  font-family: 'MedievalSharp', cursive; font-weight: bolder;
  background-color: #f1e6b4; color: #4c3e06;
  width: 90%; box-sizing: border-box;
}

.submit-button {
  padding: 0.75rem 1.5rem; font-size: 1rem; background-color: #b74d30; color: white;
  border: 1px solid #8e7513; border-radius: 10px; cursor: pointer; margin-bottom: 1rem;
  font-family: 'MedievalSharp', cursive; transition: all 0.2s ease;
  box-shadow: 0 2px 4px rgba(0,0,0,0.2);
}
.submit-button:hover:not(:disabled) { background-color: #7e6f34; transform: translateY(-1px); }
.submit-button:disabled { opacity: 0.7; cursor: not-allowed; }

.play-button { display: flex; justify-content: center; margin-top: 1rem; gap: 1rem; }

.output {
  width: 100%; max-height: 300px; overflow-y: auto;
  padding: 1rem; margin-top: 1rem;
  background-color: rgba(110,97,50,0.7); color: white;
  border-radius: 10px; border: 1px solid #000; box-sizing: border-box;
  font-family: 'MedievalSharp', cursive;
}
.output h3 { margin: 0 0 0.5rem; color: #f1e6b4; }
.output p { margin: 0; }

/* Abilities and dice on right */
.right-rail {
  position: fixed;
  right: 15%;
  top: 250px;
  width: 540px;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  z-index: 900;
}

.rail-panel {
  background-color: rgba(163,148,95,0.9);
  border: 1px solid rgba(255,255,255,0.2);
  border-radius: 8px;
  padding: 1rem;
  box-shadow: 0 1px 2px rgba(0,0,0,0.15);
  color: #392401;
  font-family: 'MedievalSharp', cursive;
}

/* Dice */
.dice-widget { position: static; width: 100%; }
.dice-buttons { display: flex; flex-wrap: wrap; gap: 0.5rem; justify-content: center; }
.dice-button {
  flex: 1 0 30%; padding: 0.75rem; font-size: 1rem;
  background-color: #b74d30; color: white; border: none; border-radius: 6px; cursor: pointer;
}
.dice-button:hover { background-color: #369f6e; }
.dice-result { margin-top: 1rem; text-align: center; font-weight: bold; }

/* Abilities */
.abilities-section { width: 100%; margin: 0; }
.ability-list { display: grid; grid-template-columns: 1fr; gap: 0.75rem; }

.ability-card {
  border: 1px solid #695710; border-radius: 10px;
  padding: 0.75rem 0.9rem 1rem; background: rgba(110,97,50,0.25);
}
.ability-card__header {
  display: flex; align-items: baseline; justify-content: space-between;
  margin-bottom: 0.5rem; color: #392401;
}
.ability-card__role { color: #e0d5b7; font-size: 0.9rem; }

.ability-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 0.5rem; }
.ability-box {
  text-align: center; border: 1px solid #695710; border-radius: 8px;
  padding: 0.5rem 0.4rem; background: #f1e6b4; color: #392401;
}
.ability-label { font-size: 0.75rem; font-weight: 700; letter-spacing: 0.03em; color: #6b5710; }
.ability-score { font-size: 1.1rem; font-weight: 800; line-height: 1.3; }
.ability-mod { display: block; font-size: 0.75rem; font-weight: 600; color: #4c3e06; }

/* + / − controls */
.ability-controls {
  display: flex;
  gap: 0.4rem;
  justify-content: center;
  margin-top: 0.4rem;
}
.ability-stepper {
  padding: 0.2rem 0.5rem;
  line-height: 1;
  border: 1px solid #695710;
  border-radius: 6px;
  background: #b74d30;
  color: #fff;
  cursor: pointer;
  font-family: 'MedievalSharp', cursive;
}
.ability-stepper:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

@media (max-width: 900px) {
  .right-rail { position: static; width: auto; margin: 1rem; }
}
</style>
