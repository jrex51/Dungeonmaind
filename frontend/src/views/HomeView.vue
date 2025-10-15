<script setup lang="ts">
import {computed, ref, render} from 'vue'
import { onMounted, onUnmounted } from 'vue'
import { useSessionStore } from '@/stores/session.ts'
import { useRouter } from 'vue-router'
import { SERVER_CONFIG } from '../config/config'
import { marked } from 'marked'


const router = useRouter()
const store = useSessionStore()
const userInput = ref<string>('')
const modelOutput = ref<string>('')
let modelOutputRendered = ref<string>('')
const isLoading = ref<boolean>(false)
const askRulebook = ref<boolean>(false)
let socket: WebSocket;

const selectedAudioFile = ref<File | null>(null)
const audioUploadStatus = ref<string>('')

const micPermissionStatus = ref('')
const isRecording = ref(false)
const audioStream = ref<MediaStream | null> (null)
const mediaRecorder = ref<MediaRecorder | null >(null)
const audioChunks = ref<Blob[]>([])
const recordedAudioURL = ref<string | null>(null)
const currentAudio = ref<HTMLAudioElement | null>(null)

const audioRecorderInterval: Ref<number | null> = ref(null);
const isFinalStop = ref(false)

const diceResult = ref<string>('')

//const backendMarkdown = ref<string>('')
//let renderedMarkdown = ref<string>('')
const backendMarkdown = ref<string[]>([])
const currentMarkdownIndex = ref(0)
let renderedMarkdown = ref('')



function goToConfig() {
  router.push('/config')
}

function goToRulebook() {
  router.push('/rulebook')
}

// socket = new WebSocket(wsUrl(SERVER_CONFIG.BASE_URL, SERVER_CONFIG.ENDPOINTS.WS_PLAYERS));
// socket.onmessage = (ev) => console.log("WS", ev.data);

onMounted(() => {
  socket = new WebSocket(wsUrl(
    SERVER_CONFIG.BASE_URL,
    SERVER_CONFIG.ENDPOINTS.WS_PLAYERS
  ));

  socket.onopen = () => {
    store.loadPlayers();        // ← holt die IST-Spielerliste
  };

  socket.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "join") {
      // Duplizate vermeiden:
      if (!store.players.some(p => p.id === msg.player.id)) {
        store.players.push(msg.player);
      }
    } else if (msg.type === "leave") {
      store.players = store.players.filter(
        p => p.id !== msg.player_id
      );
    }
  };
});

onUnmounted(() => { socket?.close()

  //Cleanly end recorder/mic on unmount
  if (mediaRecorder.value && mediaRecorder.value.state !== 'inactive') {
    isFinalStop.value = true
    try { mediaRecorder.value.requestData(); } catch {}
    mediaRecorder.value.stop();
  }

  if (recordedAudioURL.value) {
        URL.revokeObjectURL(recordedAudioURL.value);
        recordedAudioURL.value = null;
    }

  if (audioRecorderInterval.value) {
    clearInterval(audioRecorderInterval.value!)
    audioRecorderInterval.value = null
  }
})

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
        input_string: userInput.value,
        use_rulebook: askRulebook.value
      }),
    })
    if (askRulebook.value) {
      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`)
      }
    } else {
      if (!response.ok || !response.body) {
        throw new Error(`Request failed with status ${response.status}`)
      }
    }


    if(askRulebook.value) {
      //const markdownJson = await response.text()
      const markdownJson = await response.json()
      console.log(markdownJson)
      //backendMarkdown.value = markdownJson.markdown_text || ""
      //backendMarkdown.value = markdownJson
      backendMarkdown.value = markdownJson.markdown_texts || []
      if (backendMarkdown.value.length > 0) {
        currentMarkdownIndex.value = 0
        renderedMarkdown.value = marked.parse(backendMarkdown.value[0])
      }
      //if (backendMarkdown.value.trim()) {
      //  renderedMarkdown.value = marked.parse(backendMarkdown.value)
      //  console.log(renderedMarkdown.value)
      //}
    } else {
      if(!response.body) {
        throw new Error(`Request failed with status ${response.status}`)
      }
      // Removes any still shown previous rulebook searches.
      backendMarkdown.value = []
      renderedMarkdown.value = ""

      const reader = response.body.getReader()
      const decoder = new TextDecoder('utf-8')
      while (true) {
        const {done, value} = await reader.read()
        if (done) break
        const chunk = decoder.decode(value, {stream: true})
        modelOutput.value += chunk
        modelOutputRendered = marked.parse(modelOutput.value)
      }
    }
  } catch (error) {
    console.error('Error calling LLM endpoint:', error)
    modelOutput.value = 'Error calling model, error: ' + error
  } finally {
    isLoading.value = false //  unlock after done
  }
}

function showNextMarkdown() {
  if (currentMarkdownIndex.value < backendMarkdown.value.length - 1) {
    currentMarkdownIndex.value++
    renderedMarkdown.value = marked.parse(backendMarkdown.value[currentMarkdownIndex.value])
  }
}

function showPrevMarkdown() {
  if (currentMarkdownIndex.value > 0) {
    currentMarkdownIndex.value--
    renderedMarkdown.value = marked.parse(backendMarkdown.value[currentMarkdownIndex.value])
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

async function startRecording() {
  try {
    isFinalStop.value = false

    if(recordedAudioURL.value){
      URL.revokeObjectURL(recordedAudioURL.value)
      recordedAudioURL.value = null
    }
    audioChunks.value = []

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    micPermissionStatus.value = 'Microphone access granted.';
    audioStream.value = stream;

    const supportedMimeTypes = [
      'audio/ogg;codecs=opus',
      'audio/webm;codecs=opus',
      'audio/webm'
    ];
    let mimeType: string | undefined = undefined;
    for (const type of supportedMimeTypes) {
      if (MediaRecorder.isTypeSupported(type)) {
        mimeType = type;
        break;
      }
    }
    if (!mimeType) {
      console.error('No supported audio type found.');
      micPermissionStatus.value = 'No supported audio format.';
      stream.getTracks().forEach(track => track.stop());
      return;
    }

    mediaRecorder.value = new MediaRecorder(stream, { mimeType });

    mediaRecorder.value.ondataavailable = (e) => {
      if (e.data.size > 0) {
        audioChunks.value.push(e.data);
      }
    };

    mediaRecorder.value.onstop = () => {
      if (audioChunks.value.length > 0) {
        const audioBlob = new Blob(audioChunks.value, { type: mediaRecorder.value?.mimeType });
        sendAudioChunk(audioBlob);
      }

      if (isFinalStop.value) {
        isRecording.value = false;

        if (audioStream.value) {
          audioStream.value.getTracks().forEach(track => track.stop());
          const finalBlob = new Blob(audioChunks.value, { type: mediaRecorder.value?.mimeType })
          recordedAudioURL.value = URL.createObjectURL(finalBlob)
          audioChunks.value = [];
        }
      } else {
        audioChunks.value = [];
        mediaRecorder.value?.start();
      }
    };
    mediaRecorder.value.start();
    isRecording.value = true;

    setTimeout(() => {
        if (mediaRecorder.value && mediaRecorder.value.state === 'recording') {
            mediaRecorder.value.requestData();
        }
    }, 250);

    const spliceTime = 5 * 60 * 1000;
    audioRecorderInterval.value = setInterval(rotateRecording, spliceTime);

  } catch (error) {
    console.error('Microphone access denied:', error);
    micPermissionStatus.value = 'Microphone access required';
  }
}

function rotateRecording() {
  if (mediaRecorder.value && mediaRecorder.value.state === 'recording') {

    mediaRecorder.value.requestData();
    mediaRecorder.value.stop();
  }
}

function stopRecording() {
  if (mediaRecorder.value && mediaRecorder.value.state !== 'inactive') {
    isFinalStop.value = true
    if (audioRecorderInterval.value) {
      clearInterval(audioRecorderInterval.value);
      audioRecorderInterval.value  = null
    }
    mediaRecorder.value.requestData();
    mediaRecorder.value.stop();
  }
}

async function sendAudioChunk(chunk: Blob) {
  const formData = new FormData()
  const fileExtension = chunk.type.split('/')[1]?.split(';')[0] || 'ogg';
  formData.append('audio', chunk, `chunk_${Date.now()}.${fileExtension}`);

  try {
    const response = await fetch(`${SERVER_CONFIG.BASE_URL}${SERVER_CONFIG.ENDPOINTS.TRANSCRIBE_AUDIO_FILE}`, {
      method: 'POST',
      body: formData
    })

    if (!response.ok) {
      console.error('Chunk upload failed with status:', response.status)
      return
    }

    const result = await response.json()
    console.log('Chunk transcribed successfully:', result)

  } catch (error) {
    console.error('Error sending audio chunk:', error)
  }
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

/*async function transcribeRecording() {
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
}*/

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
          @keyup.enter="handleLLMQuestionSubmit"
        />
        <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
            <input type="checkbox" v-model="askRulebook" />
            show matching rulebook pages
        </label>
        <button @click="handleLLMQuestionSubmit" class="submit-button" :disabled="isLoading">
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
      <!-- Nur Leader sieht das -->
      <div v-if="store.isLeader" class="content-section">
        <h2> Record Using Microphone</h2>
        <button @click="startRecording" v-if="!isRecording" class="submit-button"> Start Recording </button>
        <button @click="stopRecording" v-if="isRecording" class="submit-button"> Stop Recording </button>

        <div v-if="isRecording" class="output">
          <p> Recording in progress </p>
        </div>

        <div v-if="micPermissionStatus" class="output">
          <p>{{ micPermissionStatus }} </p>
        </div>

        <div v-if="recordedAudioURL" class="output">
          <p>Recording completed </p>
        </div>

        <div v-if="recordedAudioURL" class="play-button">
          <button @click="playRecording" class="submit-button"> Play Recording </button>
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
      </div> <!-- Close content-section before dice-widget -->

      <div class="dice-widget">
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
    </div> <!-- Close centered-content -->
  </div> <!-- Close container -->
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
  font-weight: bold;
  font-weight: 400;
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

.dice-widget {
  position: fixed;
  right: 25%;
  top: 43%;
  transform: translateX(20%);
  background-color: rgba(163, 148, 95, 0.9);
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
  font-size: 1rem;
  background-color: #b74d30;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
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
