<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useSessionStore } from '@/stores/session.ts'
import { useRouter } from 'vue-router'
import { SERVER_CONFIG } from '../config/config'

const router = useRouter()
const store = useSessionStore()
const userInput = ref<string>('')
const modelOutput = ref<string>('')
const isLoading = ref<boolean>(false)
let socket: WebSocket | null = null;
let pingTimer: number | null = null;

const selectedAudioFile = ref<File | null>(null)
const audioUploadStatus = ref<string>('')

const micPermissionStatus = ref('')
const isRecording = ref(false)
const audioStream = ref<MediaStream | null> (null)
const mediaRecorder = ref<MediaRecorder | null >(null)
const audioChunks = ref<Blob[]>([])
const recordedAudioURL = ref<string | null>(null)
const currentAudio = ref<HTMLAudioElement | null>(null)

const diceResult = ref<string>('')

function goToConfig() {
  router.push('/config')
}



onMounted(() => {

  // Guard: ohne Player -> zurück zum Login
  const p = store.currentPlayer;
  if (!p) {
    router.push({ name: 'login' });
    return;
  }

  const url = new URL(SERVER_CONFIG.ENDPOINTS.WS_PLAYERS, SERVER_CONFIG.BASE_URL);
  url.search = new URLSearchParams({
    player_id: p.id,
    name: p.name,
    role: p.role,
  }).toString();

  socket = new WebSocket(url.toString());

  socket.onopen = async () => {
    store.loadPlayers();        // ← holt die IST-Spielerliste

    pingTimer = window.setInterval(() => {    // ← Hearbeat alle 15s
      try { socket?.send('ping'); } catch {}
    }, 15000);
  };

  socket.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "join") {
      // Duplizate vermeiden:
      if (!store.players.some(p => p.id === msg.player.id)) {
        store.players.push(msg.player);
      } else {
        // falls der Join Player-Objekt neuere Felder bringt
        store.players = store.players.map(p => p.id === msg.player.id ? msg.player : p);
      }
    } else if (msg.type === "leave") {
      store.players = store.players.filter(
        p => p.id !== msg.player_id
      );
    } else if (msg.type === "health/update") {
      store.patchPlayer(msg.player_id, {
        hp: Number(msg.hp),
        max_hp: Number(msg.max_hp),
        temp_hp: Number(msg.temp_hp),
      });
    } else if (msg.type === "attributes/update") {
      store.patchPlayer(msg.player_id, { attributes: msg.attributes });
    }
  };

  socket.onclose = () => {
    if (pingTimer) { clearInterval(pingTimer); pingTimer = null; }
    socket = null;
  };
});

onUnmounted(() => {
  if (pingTimer) { clearInterval(pingTimer); pingTimer = null; }
  try { socket?.close(); } catch {}
  socket = null;
});

function wsUrl(baseHttpUrl: string, path: string): string {
  const u = new URL(baseHttpUrl);                 // http://192.168.1.5:8000
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";  // → ws://…
  u.pathname = path.startsWith("/") ? path : `/${path}`;  // /ws/players
  return u.toString();                            // ws://192.168.1.5:8000/ws/players
}


async function onLeave() {
  await store.leave();
  router.push({ name: "login" });
}

async function handleLLMQuestionSubmit() {
  if (isLoading.value) return // prevent spamming the button
  isLoading.value = true
  modelOutput.value = ''

  try {
    const response = await fetch(`${SERVER_CONFIG.BASE_URL}${SERVER_CONFIG.ENDPOINTS.RUN_LLM}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        player_id: store.currentPlayer?.id,
        input_string: userInput.value
      }),
    })
    if (!response.ok || !response.body) {
      throw new Error(`Request failed with status ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    while (true) {
      const {done, value} = await reader.read()
      if (done) break
      const chunk = decoder.decode(value, {stream: true})
      modelOutput.value += chunk
    }
  } catch (error) {
    console.error('Error calling LLM endpoint:', error)
    modelOutput.value = 'Error calling model, error: ' + error
  } finally {
    isLoading.value = false //  unlock after done
  }
}

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

function rollDice(sides: number) {
  const result = Math.floor(Math.random() * sides) + 1
  diceResult.value = `W${sides} → ${result}`
}

/* Ability Overview */
type Dict = Record<string, unknown>
type AbilitySpec = {
  key: 'str'|'dex'|'con'|'int'|'wis'|'cha'
  label: string
  aliases: string[]
}

const ABILITIES: AbilitySpec[] = [
  { key: 'str', label: 'STR', aliases: ['strength'] },
  { key: 'dex', label: 'DEX', aliases: ['dexterity'] },
  { key: 'con', label: 'CON', aliases: ['constitution'] },
  { key: 'int', label: 'INT', aliases: ['intelligence'] },
  { key: 'wis', label: 'WIS', aliases: ['wisdom'] },
  { key: 'cha', label: 'CHA', aliases: ['charisma'] },
]

// Guards + helpers
const isRecord = (v: unknown): v is Dict =>
  v !== null && typeof v === 'object' && !Array.isArray(v)
const toNum = (v: unknown): number | undefined => {
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'string' && v.trim() !== '') {
    const n = Number(v)
    if (Number.isFinite(n)) return n
  }
  return undefined
}

// Find a property with any of the candidate names (case-insensitive)
function findKeyCI(obj: Dict, candidates: string[]): string | undefined {
  const map = new Map<string, string>()
  for (const k of Object.keys(obj)) map.set(k.toLowerCase(), k)
  for (const c of candidates) {
    const hit = map.get(c.toLowerCase())
    if (hit) return hit
  }
  return undefined
}

function pickRecordCI(obj: Dict | undefined, candidates: string[]): Dict | undefined {
  if (!obj) return undefined
  const key = findKeyCI(obj, candidates)
  if (!key) return undefined
  const v = obj[key]
  return isRecord(v) ? v : undefined
}

function readAbilityFrom(rec: Dict | undefined, spec: AbilitySpec): number | undefined {
  if (!rec) return undefined
  const key = findKeyCI(rec, [spec.key, ...spec.aliases])
  if (!key) return undefined
  return toNum(rec[key])
}

function extractAbilities(player: unknown) {
  const base = isRecord(player) ? player : undefined
  const containers: Array<Dict | undefined> = [
    pickRecordCI(base, ['abilities', 'abilityScores', 'attributes', 'attrs', 'stats']),
    base, // top level fallback
  ]
  return ABILITIES.map(spec => {
    let score: number | undefined
    for (const c of containers) {
      score = readAbilityFrom(c, spec)
      if (score !== undefined) break
    }
    const mod = score !== undefined ? Math.floor((score - 10) / 2) : undefined
    return { ...spec, score, mod }
  })
}

// visible players = all if Leader, else just current
const visiblePlayers = computed(() => {
  const players = store.players ?? [];
  if (store.isLeader) {
    const selfId = store.currentPlayer?.id;
    return players.filter((p: any) => {
      const isSelf = selfId != null && p?.id === selfId;
      const role = typeof p?.role === 'string' ? p.role.toLowerCase() : '';
      const isLeaderRole = role === 'leader';
      return !isSelf && !isLeaderRole; // nur Members übrig lassen
    });
  }
  return store.currentPlayer ? [store.currentPlayer] : [];
});


// helper exposed to the template
function getAbilityData(p: unknown) {
  return extractAbilities(p)
}


/* Healthbar */
async function damage(playerId: string, amount: number) {
  await fetch(`${SERVER_CONFIG.BASE_URL}${SERVER_CONFIG.ENDPOINTS.PLAYERS}/${playerId}/damage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ damage: amount }),
  });
}

async function heal(playerId: string, amount: number) {
  await fetch(`${SERVER_CONFIG.BASE_URL}${SERVER_CONFIG.ENDPOINTS.PLAYERS}/${playerId}/heal`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ heal: amount }),
  })
}
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
        <h2>Hallo, {{ store.currentPlayer?.name }}!</h2>
        <p v-if="store.isLeader">Du bist Leader.</p>
        <button class="submit-button" @click="onLeave">Leave</button>
        <h3>Spieler</h3>
        <ul>
          <li v-for="p in store.players" :key="p.id">
            {{ p.name }} ({{ p.role }})
          </li>
        </ul>
      </section>

      <!-- Left: main LLM -->
      <div class="content-section">
        <h2>Ask Something about the DnD-Session</h2>
        <input v-model="userInput" type="text" placeholder="Type something..." class="input-field" />
        <button @click="handleLLMQuestionSubmit" class="submit-button" :disabled="isLoading">
          {{ isLoading ? 'Loading...' : 'Submit' }}
        </button>
        <div v-if="modelOutput" class="output">
          <h3>Model Output:</h3>
          <p>{{ modelOutput }}</p>
        </div>
      </div>

      <hr style="margin: 2rem 0" />

      <!-- Only Leader: ARecording/Upload -->
      <div v-if="store.isLeader" class="content-section">
        <h2>Record Using Microphone</h2>
        <button @click="startRecording" v-if="!isRecording" class="submit-button">Start Recording</button>
        <button @click="stopRecording" v-if="isRecording" class="submit-button">Stop Recording</button>

        <div v-if="isRecording" class="output"><p>Recording in progress</p></div>
        <div v-if="micPermissionStatus" class="output"><p>{{ micPermissionStatus }}</p></div>
        <div v-if="recordedAudioURL" class="output"><p>Recording completed</p></div>

        <div v-if="recordedAudioURL" class="play-button">
          <button @click="playRecording" class="submit-button">Play Recording</button>
          <button @click="transcribeRecording" class="submit-button">Transcribe Recording</button>
        </div>

        <hr style="margin: 2rem 0" />

        <h2>Upload Audio File</h2>
        <input type="file" accept="audio/*" @change="onAudioFileChange" class="input-field" />
        <button @click="handleAudioUpload" class="submit-button">Upload Audio</button>
        <div v-if="audioUploadStatus" class="output"><p>{{ audioUploadStatus }}</p></div>
      </div>
    </div>

    <!-- Right: abilities, health and dice -->
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
                  <span>{{ a.score ?? '-' }}</span>
                  <small v-if="a.mod !== undefined" class="ability-mod">
                    ({{ a.mod >= 0 ? '+' + a.mod : a.mod }})
                  </small>
                </div>
              </div>
            </div>

            <div class="healthbar">
              <div class="healthbar__label">HP</div>
              <div class="healthbar__track">
                <div
                  class="healthbar__fill"
                  :style="{ width: Math.min(100, Math.round(((p.hp + (p.temp_hp ?? 0)) / Math.max(1, p.max_hp)) * 100)) + '%' }"
                  :title="`HP ${p.hp}/${p.max_hp}${p.temp_hp ? ` (+${p.temp_hp} temp)` : ''}`"
                />
              </div>
              <div class="healthbar__numbers">
                {{ p.hp }} / {{ p.max_hp }} <span v-if="p.temp_hp">(+{{ p.temp_hp }})</span>
              </div>

              <!-- Controls: Leader kann alle editieren, Member nur sich selbst -->
              <div class="healthbar__controls" v-if="store.isLeader || p.id === store.currentPlayer?.id">
                <button @click="damage(p.id, 1)">-1</button>
                <button @click="heal(p.id, 1)">+1</button>
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
  max-height: 90vh; /* limits height to viewport height minus some margin */
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
  margin-top: 60px; /* unter dem Header */
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
  top: 250px;            /* etwas unter dem Header (50px) */
  width: 340px;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  z-index: 900;         /* unter dem Header */
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

@media (max-width: 900px) {
  .right-rail { position: static; width: auto; margin: 1rem; }
}
</style>
