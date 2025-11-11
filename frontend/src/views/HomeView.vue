<script setup lang="ts">
import { ref, onMounted, onUnmounted, onWatcherCleanup } from 'vue'
import { useSessionStore } from '@/stores/session.ts'
import { useRouter } from 'vue-router'
import { SERVER_CONFIG } from '../config/config'
import { marked } from 'marked'
import { useRecorderStore } from '@/stores/recorder.ts'

const router = useRouter()
const store = useSessionStore()
const recorder = useRecorderStore()

const userInput = ref<string>('')
const modelOutput = ref<string>('')
let modelOutputRendered = ref<string>('')
const isLoading = ref<boolean>(false)
const askRulebook = ref<boolean>(false)

let socket: WebSocket

const selectedAudioFile = ref<File | null>(null)
const audioUploadStatus = ref<string>('')

const diceResult = ref<string>('')

// Rulebook markdown
let renderedMarkdown = ref<string>('')
const backendMarkdown = ref<string[]>([])
const currentMarkdownIndex = ref(0)

function goToConfig() { router.push('/config') }
function goToPlayers() { router.push('/players') }
function goToRulebook() { router.push('/rulebook') }

function wsUrl(baseHttpUrl: string, path: string): string {
const u = new URL(baseHttpUrl)
u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:'
u.pathname = path.startsWith('/') ? path : `/${path}`
return u.toString()
}

onMounted(() => {
  socket = new WebSocket(wsUrl(
    SERVER_CONFIG.BASE_URL,
    SERVER_CONFIG.ENDPOINTS.WS_PLAYERS
  ));

socket.onopen = () => {
store.loadPlayers()
}

socket.onmessage = (ev) => {
const msg = JSON.parse(ev.data)
if (msg.type === 'join') {
if (!store.players.some(p => p.id === msg.player.id)) {
store.players.push(msg.player)
}
} else if (msg.type === 'leave') {
store.players = store.players.filter(p => p.id !== msg.player_id)
}
}
})

onUnmounted(() => {
socket?.close()
})

async function handleQuestionSubmit() {
if (isLoading.value) return
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
isLoading.value = false
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
isLoading.value = false
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
if (!response.ok) throw new Error(`Upload failed with status ${response.status}`)
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


async function onLeave() {
  recorder.stopRecording() //stop recording when leaving session
  await store.leave();
  router.push({ name: "login" });
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
         <button class="players-button" @click="goToPlayers">Players</button>
         <button class="config-button" @click="goToConfig">Config</button>
       </div>
    </div>

    <div class="centered-content">
      <section>
        <h2>Hello {{ store.currentPlayer?.name }}</h2>
        <p v-if="store.isLeader">Du bist Leader.</p>

        <button @click="onLeave">Verlassen</button>

        <h3>Spieler</h3>
        <ul>
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
            <button @click="showPrevMarkdown" :disabled="currentMarkdownIndex === 0">Previous</button>
            <span>{{ currentMarkdownIndex + 1 }} / {{ backendMarkdown.length }}</span>
            <button @click="showNextMarkdown" :disabled="currentMarkdownIndex === backendMarkdown.length - 1">Next</button>
          </div>
          <div v-html="renderedMarkdown"></div>
        </div>
      </div>

      <hr style="margin: 2rem 0" />
            <div v-if="store.isLeader" class="content-section">
        <h2> Record Using Microphone</h2>
        
        <div class="recording-controls">
          <button @click="startRecording" v-if="!recorder.isRecording" class="submit-button"> Start Recording </button>
          <button @click="stopRecording" v-if="recorder.isRecording" class="submit-button"> Stop Recording  </button> 
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

      <div v-if="store.isLeader" class="content-section">
        <h2>Upload Audio File</h2>
        <input type="file" accept="audio/*" @change="onAudioFileChange" class="input-field" />
        <button @click="handleAudioUpload" class="submit-button">Upload Audio</button>

        <div v-if="audioUploadStatus" class="output">
          <p>{{ audioUploadStatus }}</p>
        </div>
      </div>       <div class="dice-widget">
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
    </div>   </div> </template>


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
  gap: 0.5rem;
}

.centered-content {
  background-color: rgba(163, 148, 95, 0.8);
  padding: 2rem;
  border-radius: 8px;
  max-width: 600px;
  width: 100%;
  box-sizing: border-box;
  border: 1px solid rgba(255, 255, 255, 0.2);
  box-shadow: 0 4px 30px rgba(0, 0, 0, 0.4);
}


.rulebook-button,
.players-button,
.config-button {
  padding: 0.5rem 1rem;
  background-color: rgba(53, 73, 94, 0.9);
  border: 1px solid #4a575e;
  border-radius: 4px;
  color: white;
  cursor: pointer;
  font-family: 'MedievalSharp', cursive;
  font-weight: normal;
  transition: background-color 0.3s ease;
}

.rulebook-button:hover,
.players-button:hover,
.config-button:hover {
  background-color: #4a575e;
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
  margin-top: 0;
  margin-bottom: 1.5rem;
  font-family: 'MedievalSharp', cursive;
  font-weight: bolder;
}


h2 {
  color: #392401;
  text-align: center;
  margin-top: 0;
  font-size: x-large;
  margin-bottom: 1.5rem;
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
  font-weight: normal;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
  transition: all 0.2s ease;
}

.submit-button:hover:not(:disabled) {
  background-color: #7e6f34;
  transform: translateY(-1px);
}

.submit-button:disabled {
  opacity: 0.7;
  cursor: not-allowed;
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
  border: 1px solid #000000;
  font-family: 'MedievalSharp', cursive;
  font-size: 1.1em;
  box-sizing: border-box;
}

.output p {
  margin: 0;
}

.output h3 {
  margin-top: 0;
  margin-bottom: 0.5rem;
  color: #f1e6b4;
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
}

.recording-controls {
  display: flex;
  gap: 1rem;
  justify-content: center;
  margin-bottom: 1rem;
}

.dice-widget {
  position: fixed;
  right: 25%;
  top: 43%;
  transform: translateX(20%);
  background-color: rgba(163, 148, 95, 0.8);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 8px;
  padding: 1.5rem;
  width: 300px;
  margin-left: 2rem;
  z-index: 100;
  font-family: 'MedievalSharp', cursive;
  color: #392401;
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
  color: #8b0000; /* dark red for emphasis */
  font-weight: bold;
}

:deep(.markdown-output em) {
  color: #003366; /* dark blue */
  font-style: italic;
}

:deep(.markdown-output strong em),
:deep(.markdown-output em strong) {
  color: #800080; /* purple */
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
</style>