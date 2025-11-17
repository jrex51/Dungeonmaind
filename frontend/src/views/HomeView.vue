<script setup lang="ts">
import { ref, type Ref, computed, onMounted, onUnmounted } from 'vue'
import { type PlayerOut, updateMaxHp, damagePlayer, healPlayer, patchPlayerAbility, kickPlayer } from '../api/playersAPI.ts'
import { useSessionStore } from '@/stores/session.ts'
import { useRouter } from 'vue-router'
import { SERVER_CONFIG } from '../config/config'
import { marked } from 'marked'
import { useRecorderStore } from '@/stores/recorder.ts'

const router = useRouter()
const store = useSessionStore()
const recorder = useRecorderStore()

/** UI state */
const userInput = ref<string>('')
const modelOutput = ref<string>('')
const modelOutputRendered = ref<string>('')
const isLoading = ref<boolean>(false)
const askRulebook = ref<boolean>(false)
let socket: WebSocket | null = null;
let pingTimer: number | null = null;

const showNameModal = ref(false)
const sessionName = ref("")

/** Audio (file upload) */
const selectedAudioFile = ref<File | null>(null)
const audioUploadStatus = ref<string>('')

/** Dice */
const diceResult = ref<string>('')

/** Ability PATCH*/
const abilityBusy = ref<Record<string, boolean>>({})

// Rulebook markdown
const backendMarkdown = ref<string[]>([])
const currentMarkdownIndex = ref(0)
const renderedMarkdown = ref('')

function apiBase(): string {
  return store.backendUrl ?? SERVER_CONFIG.BASE_URL
}

function goToConfig() { 
  router.push('/config') 
}

function goToPlayers() { 
  router.push('/players') 
}

function goToRulebook() { 
  router.push('/rulebook') 
}

/** Build WS URL from HTTP base + path */
function wsUrl(baseHttpUrl: string, path: string): string {
  const u = new URL(baseHttpUrl)
  u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:'
  u.pathname = path.startsWith('/') ? path : `/${path}`
  return u.toString()
}

/** WebSocket lifecycle */
onMounted(() => {
  // Guard: ohne Player -> zurück zum Login
  const p = store.currentPlayer
  if (!p) {
    router.push({ name: 'login' })
    return
  }

  // Use wsUrl() to ensure ws/wss scheme, then attach query params
  const baseWs = wsUrl(apiBase(), SERVER_CONFIG.ENDPOINTS.WS_PLAYERS)
  const url = new URL(baseWs)
  url.search = new URLSearchParams({
    player_id: p.id,
    name: p.name,
    role: p.role,
  }).toString()

  socket = new WebSocket(url.toString())

  socket.onopen = async () => {
    try {
      await store.loadPlayers() // initial list
    } catch (e) {
      console.error('loadPlayers failed', e)
    }

    try { socket?.send('ping'); } catch { }
    pingTimer = window.setInterval(() => {    // Hearbeat alle 15s
      try { socket?.send('ping'); } catch {}
    }, 15000);
  };

  socket.onmessage = (ev) => {
    const msg = JSON.parse(ev.data)

    if (msg.type === 'join') {
      // centralized in store
      store.applyWsJoin(msg.player)
    } else if (msg.type === 'leave') {
      store.applyWsLeave(msg.player_id)
    } else if (msg.type === 'update' && msg.player?.id) {
      // generic upsert path (expects full PlayerOut with nested hp)
      store.applyWsUpdate(msg.player)
    } else if (msg.type === 'health/update' && msg.hp) {
      // backend now sends nested hp directly
      store.patchPlayer(msg.player_id, { hp: msg.hp })
    }
    // no attributes/abilities mapping needed anymore
  }

  socket.onclose = (ev) => {
    if (pingTimer) { clearInterval(pingTimer); pingTimer = null; }
    // 4001 = vom Server gekickt
    if (ev.code === 4001) {
      store.forceLogout();
      router.push({ name: 'login' });
    }
    socket = null;
  };
});

onUnmounted(() => {
  if (pingTimer) { clearInterval(pingTimer); pingTimer = null; }
  try { socket?.close(); } catch {}
  socket = null;
})

/** Session actions */
async function onLeave() {
  recorder.stopRecording() //stop recording when leaving session
  await store.leave()
  await router.push({ name: 'login' })
}

async function onExport() {
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

async function handleQuestionSubmit() {
  if (isLoading.value) return  // prevent spamming the button
  isLoading.value = true
  modelOutput.value = ''

  if (askRulebook.value) {
    try {
      const response = await fetch(`${SERVER_CONFIG.BASE_URL}${SERVER_CONFIG.ENDPOINTS.RULEBOOK_SEARCH}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ input_string: userInput.value }),
      })
      if (!response.ok) throw new Error(`Request failed with status ${response.status}`)

      const markdownJson = await response.json()
      backendMarkdown.value = markdownJson.markdown_texts || []
      if (backendMarkdown.value.length > 0) {
        currentMarkdownIndex.value = 0
        renderedMarkdown.value = await marked.parse(backendMarkdown.value[0]) as string
      }
    } catch (error) {
      console.error('Error calling Rulebook Search endpoint:', error)
    } finally {
      isLoading.value = false //  unlock after done
    }
  } else {
    try {
      const response = await fetch(`${SERVER_CONFIG.BASE_URL}${SERVER_CONFIG.ENDPOINTS.RUN_LLM}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          player_id: store.currentPlayer?.id,
          input_string: userInput.value,
          use_rulebook: askRulebook.value
        }),
      })
      if (!response.ok || !response.body) throw new Error(`Request failed with status ${response.status}`)

       // Removes any still shown previous rulebook searches.
      backendMarkdown.value = []
      renderedMarkdown.value = ''

      const reader = response.body.getReader()
      const decoder = new TextDecoder('utf-8')
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value, { stream: true })
        modelOutput.value += chunk
        modelOutputRendered.value = marked.parse(modelOutput.value) as string
      }
    } catch (error) {
      console.error('Error calling LLM endpoint:', error)
      modelOutput.value = 'Error calling model, error: ' + error
    } finally {
      isLoading.value = false  //  unlock after done
    }
  }
}

function showNextMarkdown() {
  if (currentMarkdownIndex.value < backendMarkdown.value.length - 1) {
    currentMarkdownIndex.value++
    renderedMarkdown.value = marked.parse(backendMarkdown.value[currentMarkdownIndex.value]) as string
  }
}

function showPrevMarkdown() {
  if (currentMarkdownIndex.value > 0) {
    currentMarkdownIndex.value--
    renderedMarkdown.value = marked.parse(backendMarkdown.value[currentMarkdownIndex.value]) as string
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
    const response = await fetch(
      `${SERVER_CONFIG.BASE_URL}${SERVER_CONFIG.ENDPOINTS.TRANSCRIBE_AUDIO_FILE}`,
      {
        method: 'POST',
        body: formData,
      },
    )
    if (!response.ok) {
      throw new Error(`Upload failed with status ${response.status}`)
    }
    const result = await response.json()
    audioUploadStatus.value = `Upload successful: ${result.message || 'Audio file received'}`
  } catch (error) {
    console.error('An error occurred while uploading your audio file:', error)
    audioUploadStatus.value = 'Upload error'
  }
}

function onAudioFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  selectedAudioFile.value = (target?.files && target.files.length > 0) ? target.files[0] : null
}

async function startRecording() {
  await recorder.startRecording()
}

function stopRecording() { 
  recorder.stopRecording() 
}

function playRecording() { 
  recorder.playRecording() 
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
  const ability = p?.abilities ?? {}
  return ABILITIES.map((spec) => {
    const score = typeof ability[spec.key] === 'number' ? ability[spec.key] : undefined
    const mod = score !== undefined ? Math.floor((score - 10) / 2) : undefined
    return { ...spec, score, mod }
  })
}

/** Ability change */
async function patchAbility(playerId: string, key: AbilitySpec['key'], value: number) {
  if (!playerId) return
  abilityBusy.value[key] = true
  try {
    await patchPlayerAbility(playerId, key, value, apiBase())
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

/* Healthbar */
async function damage(playerId: string, amount: number) {
  try {
    await damagePlayer(playerId, amount, apiBase())
  } catch (e) {
    console.error('Damage failed:', e)
  }
}

async function heal(playerId: string, amount: number) {
  try {
    await healPlayer(playerId, amount, apiBase())
  } catch (e) {
    console.error('Heal failed:', e)
  }
}

function clamp(n: number, min: number, max: number) {
  return Math.min(max, Math.max(min, n))
}

function hpPct(p: any) {
  const max = Math.max(1, Number(p?.hp?.max ?? 0))
  const curr = clamp(Number(p?.hp?.current ?? 0), 0, max)
  return Math.round((curr / max) * 100)
}

function tempPct(p: any) {
  const max = Math.max(1, Number(p?.hp?.max ?? 0))
  const curr = clamp(Number(p?.hp?.current ?? 0), 0, max)
  const temp = Math.max(0, Number(p?.hp?.temp ?? 0))
  const total = Math.min(curr + temp, max)
  return Math.max(0, Math.round((total / max) * 100) - Math.round((curr / max) * 100))
}

function hpClass(p: any) {
  const pct = hpPct(p)
  if (pct <= 30) return 'is-low'
  if (pct <= 60) return 'is-mid'
  return 'is-high'
}

async function onMaxHpChange(player: PlayerOut, event: Event) {
  const input = event.target as HTMLInputElement
  const raw = parseInt(input.value, 10)

  // Basic guard on the client; backend will enforce too
  if (!Number.isFinite(raw) || raw < 1) {
    input.value = String(player.hp.max)
    return
  }

  try {
    const updated = await updateMaxHp(player.id, raw, apiBase())

    const index = store.players.findIndex((p: PlayerOut) => p.id === updated.id)
    if (index !== -1) {
      store.players[index] = updated
    }
  } catch (err) {
    console.error(err)
    input.value = String(player.hp.max)
  }
}

/** Kick using X-Player-Id for leader auth */
async function kick(playerId: string) {
  const actorId = store.currentPlayer?.id
  if (!actorId) {
    console.warn('Kick attempted without current player')
    return
  }
  try {
    await kickPlayer(playerId, actorId, apiBase())
  } catch (e) {
    console.error('Kick failed:', e)
  }
}

/** Dice */
function rollDice(sides: number) {
  const result = Math.floor(Math.random() * sides) + 1
  diceResult.value = `W${sides} → ${result}`
}
</script>

<template>
  <div class="container">
     <div class="header">
       <div class="header-left"></div>
       <h1>Dungeonmaind</h1>
       <div class="header-right">
         <button class="rulebook-button" @click="goToRulebook">Rulebook</button>
         <button v-if="store.isLeader" class="players-button" @click="goToPlayers">Players</button>
         <button v-if="store.isLeader" class="config-button" @click="goToConfig">Config</button>
         <button v-if="store.isLeader" class="export-button" @click="showNameModal = true">Save Session</button>
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
    </div>

    <div class="centered-content">
      <section>
        <h2>Hello {{ store.currentPlayer?.name }}</h2>
        <p v-if="store.isLeader">You are the Leader.</p>

        <button class="submit-button" @click="onLeave">Leave</button>

        <h3>Players</h3>
        <ul>
          <li v-for="p in store.players" :key="p.id">
            {{ p.name }} ({{ p.role }})
          </li>
        </ul>
      </section>

      <!-- Left: main LLM -->
      <div class="content-section">
        <h2>Ask Something about the DnD-Session</h2>
        <input
          v-model="userInput"
          type="text"
          placeholder="Type something..."
          class="input-field"
          @keyup.enter="handleQuestionSubmit"
        />
        <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
            <input type="checkbox" v-model="askRulebook" />
            show matching rulebook pages
        </label>
        <button @click="handleQuestionSubmit" class="submit-button" :disabled="isLoading">
          {{ isLoading ? 'Loading...' : 'Submit' }}
        </button>
        <div v-if="modelOutput" class="markdown-output">
          <h3>Model Output:</h3>
          <div v-html="modelOutputRendered"></div>
        </div>
        <div v-if="backendMarkdown.length" class="markdown-output scrollable-panel">
          <h3>Relevant SRD article</h3>
          <div class="markdown-navigation">
            <button @click="showPrevMarkdown" :disabled="currentMarkdownIndex === 0">
              Previous
            </button>
            <span>
              {{ currentMarkdownIndex + 1 }} /
              {{ backendMarkdown.length }}
            </span>
            <button
              @click="showNextMarkdown"
              :disabled="currentMarkdownIndex === backendMarkdown.length - 1"
            >
              Next
            </button>
          </div>
          <div v-html="renderedMarkdown"></div>
        </div>
      </div>

      <hr style="margin: 2rem 0" />

      <!-- Leader-only: recording -->
      <div v-if="store.isLeader" class="content-section">
        <h2>Record Using Microphone</h2>
        
        <div class="recording-controls">
          <button @click="startRecording" v-if="!recorder.isRecording" class="submit-button"> 
            Start Recording 
          </button>
          <button @click="stopRecording" v-if="recorder.isRecording" class="submit-button">
            Stop Recording  
          </button> 
        </div>

        <div v-if="recorder.micPermissionStatus" class="output">
          <p>{{ recorder.micPermissionStatus }}</p>
        </div>

        <div v-if="recorder.isRecording" class="recording-timer output">
          <p> Recording: {{ recorder.formattedRecordingTime }}</p>
        </div>
        
        <div v-if="recorder.recordedAudioURL" class="output">
          <p>Recording completed. Duration: {{ recorder.formattedRecordingTime }}</p>
        </div>
        
        <div v-if="recorder.recordedAudioURL" class="play-button">
          <button @click="playRecording" class="submit-button">Play Recording</button>
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
    </div>

    <!-- Right: abilities, health and dice -->
    <aside :class="['right-rail', store.isLeader ? 'right-rail--leader' : 'right-rail--member']">
      <div :class="['right-rail__inner', store.isLeader ? 'right-rail__inner--leader' : null]">
        <!-- dice -->
        <div :class="['dice-widget', 'rail-panel', !store.isLeader ? 'dice-widget--member' : null]">
          <h2 class="rail-title">Roll a dice</h2>
          <div class="dice-buttons">
            <button @click="rollDice(4)" class="dice-button">W4</button>
            <button @click="rollDice(6)" class="dice-button">W6</button>
            <button @click="rollDice(8)" class="dice-button">W8</button>
            <button @click="rollDice(12)" class="dice-button">W12</button>
            <button @click="rollDice(20)" class="dice-button">W20</button>
          </div>
          <div class="dice-result" v-if="diceResult">
            {{ diceResult }}
          </div>
        </div>

        <!-- player information -->
        <section
          :class="[
            'abilities-section',
            'rail-panel',
            !store.isLeader ? 'abilities-section--member' : null,
          ]"
        >
          <h2 class="rail-title">
            {{ store.isLeader ? 'Player Overview' : 'Your Information' }}
          </h2>

          <div v-if="visiblePlayers.length" class="ability-list">
            <div
              v-for="p in visiblePlayers"
              :key="p.id ?? p.name ?? JSON.stringify(p)"
              class="ability-card"
            >
              <div class="ability-card__header" v-if="store.isLeader">
                <div class="ability-card__name">
                  {{ p.name ?? 'Unnamed Player' }}
                </div>
              </div>
              <div class="section__label">Abilities:</div>
              <div class="ability-grid">
                <div v-for="a in getAbilityData(p)" :key="a.key" class="ability-box">
                  <div class="ability-label">
                    {{ a.label }}
                  </div>
                  <div class="ability-score">
                    <span>{{ a.score ?? '—' }}</span>
                  </div>
                  <div
                    v-if="store.isLeader || p.id === store.currentPlayer?.id"
                    class="ability-controls"
                  >
                    <button
                      class="ability-stepper"
                      :disabled="abilityBusy[a.key]"
                      @click="decAbility(p, a.key)"
                      aria-label="decrease"
                    >
                      −
                    </button>
                    <button
                      class="ability-stepper"
                      :disabled="abilityBusy[a.key]"
                      @click="incAbility(p, a.key)"
                      aria-label="increase"
                    >
                      +
                    </button>
                  </div>
                </div>
              </div>

              <div class="healthbar" :class="hpClass(p)">
                <!-- Column 1: Label -->
                <div class="section__label">Hit Points:</div>

                <!-- Column 2: Progressbar -->
                <div
                  class="healthbar__track"
                  role="progressbar"
                  :aria-valuemin="0"
                  :aria-valuemax="p.hp.max"
                  :aria-valuenow="p.hp.current"
                  :aria-valuetext="`${p.hp.current}/${p.hp.max}${
                    p.hp.temp ? ` (+${p.hp.temp})` : ''
                  }`"
                  :title="`HP ${p.hp.current}/${p.hp.max}${
                    p.hp.temp ? ` (+${p.hp.temp} temp)` : ''
                  }`"
                >
                  <div class="healthbar__fill" :style="{ width: hpPct(p) + '%' }"></div>

                  <div
                    v-if="p.hp.temp"
                    class="healthbar__temp"
                    :style="{
                      left: hpPct(p) + '%',
                      width: tempPct(p) + '%',
                    }"
                  ></div>
                </div>

                <!-- Column 3: Numbers -->
                <div class="healthbar__numbers">
                  {{ p.hp.current }} / {{ p.hp.max }}
                  <span v-if="p.hp.temp"> (+{{ p.hp.temp }}) </span>
                </div>

                <!-- Column 4: Buttons -->
                <div
                  class="healthbar__controls"
                  v-if="store.isLeader || p.id === store.currentPlayer?.id"
                >
                  <button
                    class="ability-stepper"
                    @click="damage(p.id, 1)"
                    aria-label="take 1 damage"
                  >
                    −
                  </button>
                  <button class="ability-stepper" @click="heal(p.id, 1)" aria-label="heal 1 hp">
                    +
                  </button>
                </div>
              </div>

              <div class="hpmax-row">
                <label class="section__label" :for="'hpmax-' + p.id"> Maximum Hit Points: </label>
                <input
                  :id="'hpmax-' + p.id"
                  class="hpmax-input"
                  type="number"
                  min="1"
                  :value="p.hp.max"
                  @change="onMaxHpChange(p, $event)"
                />
              </div>
              <div class="leader__controls" v-if="store.isLeader">
                <button v-if="store.isLeader && p.id !== store.currentPlayer?.id"
                        @click="kick(p.id)">Kick</button>
              </div>
            </div>
          </div>
          <p v-else class="output">No players found.</p>
        </section>
      </div>
    </aside>
  </div>
</template>

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

/* Main container */
.container {
  max-width: 600px;
  margin: 2rem auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  max-height: 90vh;
  position: relative;
}

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
.players-button,
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
.players-button:hover,
.config-button:hover,
.export-button:hover {
  background-color: #4a575e;
}

/* Centered content */
.centered-content {
  background-color: rgba(163, 148, 95, 0.8);
  padding: 2rem;
  border-radius: 8px;
  max-width: 600px;
  width: 100%;
  box-sizing: border-box;
  border: 1px solid rgba(255, 255, 255, 0.2);
  box-shadow: 0 4px 30px rgba(0, 0, 0, 0.4);
  margin-top: 60px;
}

.content-section {
  display: flex;
  flex-direction: column;
  align-items: center;
}

h1 {
  color: #392401;
  text-align: center;
  padding-top: 20px;
  margin: 0 0 1.5rem;
  font-family: 'MedievalSharp', cursive;
  font-weight: bolder;
}

h2 {
  color: #392401;
  text-align: center;
  margin: 0 0 1.5rem;
  font-size: x-large;
  font-family: 'MedievalSharp', cursive;
  font-weight: bolder;
}

hr {
  width: 100%;
  border: none;
  border-top: 1px solid rgba(94, 80, 53, 0.5);
  margin: 2rem 0;
}

.input-field {
  padding: 0.75rem;
  font-size: 1rem;
  margin-bottom: 1rem;
  border: 1px solid #695710;
  border-radius: 10px;
  font-family: 'MedievalSharp', cursive;
  font-weight: bolder;
  background-color: #f1e6b4;
  color: #4c3e06;
  width: 90%;
  box-sizing: border-box;
}

.submit-button {
  padding: 0.75rem 1.5rem;
  font-size: 1rem;
  background-color: #b74d30;
  color: white;
  border: 1px solid #8e7513;
  border-radius: 10px;
  cursor: pointer;
  margin-bottom: 1rem;
  font-family: 'MedievalSharp', cursive;
  transition: all 0.2s ease;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}

.submit-button:hover:not(:disabled) {
  background-color: #7e6f34;
  transform: translateY(-1px);
}

.submit-button:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

/* Recording specific styles */
.recording-controls {
  display: flex;
  gap: 1rem;
  justify-content: center;
  margin-bottom: 1rem;
}

.recording-timer {
  padding: 1rem;
  margin-top: 1rem;
  background-color: rgba(183, 77, 48, 0.6);
  color: white;
  border-radius: 10px;
  border: 1px solid #000000;
  font-family: 'MedievalSharp', cursive;
  font-size: 1.1em;
  box-sizing: border-box;
  text-align: center;
}

.play-button {
  display: flex;
  justify-content: center;
  margin-top: 1rem;
  gap: 1rem;
}

.output {
  width: 100%;
  max-height: 300px;
  overflow-y: auto;
  padding: 1rem;
  margin-top: 1rem;
  background-color: rgba(110, 97, 50, 0.7);
  color: white;
  border-radius: 10px;
  border: 1px solid #000;
  box-sizing: border-box;
  font-family: 'MedievalSharp', cursive;
  font-weight: 400;
}

.output p {
  margin: 0;
}

.output h3 {
  margin-top: 0;
  margin-bottom: 0.5rem;
  color: #f1e6b4;
}

/* Right rail layout */
.right-rail {
  position: fixed;
  right: 15%;
  width: 540px;
  z-index: 900;
  box-sizing: border-box;
  color: #392401;
  font-family: 'MedievalSharp', cursive;
}

/* Leader-Version: füllt vertikal den Bildschirmbereich und scrollt intern */
.right-rail--leader {
  top: 10px;
  bottom: 5px;
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 0.5rem;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.right-rail--leader::-webkit-scrollbar {
  display: none;
}

/* Player-Version: fixed */
.right-rail--member {
  top: 240px;
  bottom: auto;
  overflow: visible;
  padding-right: 0;
}

/* Gemeinsames Layout innen: Cards untereinander mit Abstand */
.right-rail__inner {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

/* Nur Leader: künstlicher Offset nach unten, damit die Box optisch nicht direkt unter dem Header klebt */
.right-rail__inner--leader {
  padding-top: 65px;
}

.rail-panel {
  background-color: rgba(163, 148, 95, 0.9);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 8px;
  padding: 1rem;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.15);
  color: #392401;
  font-family: 'MedievalSharp', cursive;
}

.rail-title {
  margin: 0 0 1rem;
  text-align: center;
  color: #392401;
  font-family: 'MedievalSharp', cursive;
  font-size: 1.45rem;
  font-weight: 800;
  letter-spacing: 0.03em;
}

/* Dice */
.dice-widget {
  position: static;
  width: 100%;
  margin-top: 3rem;
}

.dice-widget--member {
  margin-top: -20px;
}

.dice-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  justify-content: center;
}

.dice-button {
  flex: 1 0 30%;
  padding: 0.75rem;
  font-size: 1.15rem;
  background-color: #b74d30;
  color: white;
  border: 1px solid #8e7513;
  border-radius: 6px;
  cursor: pointer;
  font-family: 'MedievalSharp', cursive;
}

.dice-button:hover {
  background-color: #369f6e;
}

.dice-result {
  margin-top: 1rem;
  text-align: center;
  font-weight: bold;
}

/* Abilities */
.abilities-section {
  width: 100%;
  margin: 0;
}

.abilities-section--member {
  margin-top: 2rem;
}

.ability-list {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.75rem;
}

.ability-card {
  border: 1px solid #695710;
  border-radius: 10px;
  padding: 0.75rem 0.9rem 1rem;
  background: rgba(110, 97, 50, 0.25);
}

.ability-card__header {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  margin-bottom: 0.75rem;
  color: #392401;
}

.ability-card__name {
  font-size: 1.25rem;
  font-weight: 800;
  line-height: 1.2;
  font-family: 'MedievalSharp', cursive;
  letter-spacing: 0.03em;
  color: #392401;
}

.ability-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 0.5rem;
}

.ability-box {
  text-align: center;
  border: 1px solid #695710;
  border-radius: 8px;
  padding: 0.5rem 0.4rem;
  background: #f1e6b4;
  color: #392401;
}

.ability-label {
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.03em;
  color: #6b5710;
}

.ability-score {
  font-size: 1.1rem;
  font-weight: 800;
  line-height: 1.3;
}

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

/* Label for ability and healthbar */
.section__label {
  font-weight: 800;
  letter-spacing: 0.03em;
  color: #392401;
  font-size: 1.05rem;
}

/* Healthbar */
.healthbar {
  border-top: 1px solid rgba(57, 36, 1, 0.4);
  padding-top: 1rem;
  margin-top: 1.5rem;
  display: grid;
  grid-template-columns: auto 1fr auto auto;
  gap: 0.5rem 0.75rem;
  align-items: center;
}

.healthbar__numbers {
  justify-self: end;
  font-weight: 700;
  color: #392401;
  font-size: 1rem;
}

.healthbar__track {
  position: relative;
  height: 14px;
  border-radius: 7px;
  background: rgba(0, 0, 0, 0.2);
  outline: 1px solid #695710;
  overflow: hidden;
}

.healthbar__fill,
.healthbar__temp {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  width: 0;
  transition: width 200ms ease;
}

/* Basis-HP-Farbe (ändert sich je nach Rest-Prozent) */
.healthbar__fill {
  background: linear-gradient(180deg, #5bb45b, #2f8f2f); /* high */
}

.healthbar.is-mid .healthbar__fill {
  background: linear-gradient(180deg, #d6b34c, #b98f1e); /* mid */
}

.healthbar.is-low .healthbar__fill {
  background: linear-gradient(180deg, #d6634c, #b91e1e); /* low */
}

.healthbar__controls {
  display: flex;
  gap: 0.4rem;
  justify-self: end;
}

.healthbar__controls .ability-stepper {
  padding: 0.2rem 0.5rem;
  line-height: 1;
  min-width: 2rem;
  text-align: center;
}

/* Maximum hit points setting */
.hpmax-row {
  margin-top: 1rem;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
  border-top: 1px solid rgba(57, 36, 1, 0.4);
  padding-top: 1rem;
}

.hpmax-input {
  width: 5rem;
  padding: 0.4rem 0.5rem;
  font-size: 1rem;
  line-height: 1.2;
  text-align: center;
  border: 1px solid #695710;
  border-radius: 6px;
  background: #f1e6b4;
  color: #392401;
  font-family: 'MedievalSharp', cursive;
  font-weight: 700;
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

/* Markdown styles */
:deep(.markdown-output) {
  font-family: 'MedievalSharp', cursive;
  color: #392401;
  line-height: 1.5;
  margin-top: 1rem;
}

:deep(.markdown-output h1) {
  font-size: 2rem;
  color: #1a3b1a;
  border-bottom: 2px solid #392401;
  padding-bottom: 0.3rem;
  margin-top: 1rem;
}

:deep(.markdown-output h2) {
  font-size: 1.5rem;
  color: #2a4b2a;
  border-bottom: 1px solid #392401;
  padding-bottom: 0.2rem;
  margin-top: 1rem;
}

:deep(.markdown-output h3),
:deep(.markdown-output h4),
:deep(.markdown-output h5),
:deep(.markdown-output h6) {
  color: #3a5b3a;
  margin-top: 0.8rem;
  font-weight: bold;
}

:deep(.markdown-output strong) {
  color: #8b0000;
  font-weight: bold;
}

:deep(.markdown-output em) {
  color: #003366;
  font-style: italic;
}

:deep(.markdown-output strong em),
:deep(.markdown-output em strong) {
  color: #800080;
  font-weight: bold;
  font-style: italic;
}

:deep(.markdown-output table) {
  width: 100%;
  border-collapse: collapse;
  margin: 0.5rem 0;
  font-size: 0.95rem;
}

:deep(.markdown-output th),
:deep(.markdown-output td) {
  border: 1px solid #392401;
  padding: 0.3rem 0.5rem;
  text-align: center;
}

:deep(.markdown-output th) {
  background-color: #f5e6b4;
  font-weight: bold;
}

:deep(.markdown-output tr:nth-child(even)) {
  background-color: #faf0d4;
}

:deep(.markdown-output p) {
  margin: 0.4rem 0;
}

:deep(.markdown-output h6) {
  font-style: italic;
  color: #4b2e2e;
  margin-top: 0.5rem;
}

:deep(.scrollable-panel) {
  max-height: 400px;
  max-width: 100%;
  overflow-x: auto;
  overflow-y: auto;
  padding: 1rem;
  border: 1px solid #ccc;
  border-radius: 8px;
  background-color: rgba(110, 97, 50, 0.7);
  box-sizing: border-box;
}

:deep(.markdown-navigation) {
  display: flex;
  justify-content: space-between;
  margin-top: 0.5rem;
}

/* Responsive design */
@media (max-width: 900px) {
  .right-rail {
    position: static;
    right: auto;
    top: auto;
    bottom: auto;
    width: auto;
    margin: 1rem;
    padding-right: 0;
  }

  .right-rail--leader,
  .right-rail--member {
    overflow: visible;
  }

  .right-rail__inner--leader {
    padding-top: 0;
  }

  .container {
    max-width: 100%;
    margin: 1rem;
  }
}
</style>