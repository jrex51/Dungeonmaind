<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const userInput = ref<string>('')
const modelOutput = ref<string>('')
const isLoading = ref<boolean>(false)

const selectedAudioFile = ref<File | null>(null)
const audioUploadStatus = ref<string>('')

const micPermissionStatus = ref('')
const isRecording = ref(false)
const audioStream = ref<MediaStream | null> (null)
const mediaRecorder = ref<MediaRecorder | null >(null)
const audioChunks = ref<Blob[]>([])
const recordedAudioURL = ref<string | null>(null)
const currentAudio = ref<HTMLAudioElement | null>(null)

function goToConfig() {
  router.push('/config')
}

async function handleLLMQuestionSubmit() {
  if (isLoading.value) return // prevent spamming the button
  isLoading.value = true
  modelOutput.value = ''

  try {
    const response = await fetch('http://localhost:8000/llm/runLLM', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({input_string: userInput.value}),
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
    const response = await fetch('http://localhost:8000/processAudioData/transcribeAudioFile', {
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
  const response = await fetch('http://localhost:8000/processAudioData/transcribeAudioFile',{
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

</script>

<template>
  <div class="container">

     <div class="header">
       <div class="header-left"></div>
       <h1>Dungeonmaind</h1>
       <button class="config-button" @click="goToConfig">Config</button>
    </div>

    <h2>Enter Your Text</h2>
    <input v-model="userInput" type="text" placeholder="Type something..." class="input-field" />
    <button @click="handleLLMQuestionSubmit" class="submit-button" :disabled="isLoading">
      {{ isLoading ? 'Loading...' : 'Submit' }}
    </button>
    <div v-if="modelOutput" class="output">
      <h3>Model Output:</h3>
      <p>{{ modelOutput }}</p>
    </div>

    <hr style="margin: 2rem 0" />

    <h1> Record Using Microphone</h1>
    <button @click="startRecording" v-if="!isRecording" class="submit-button"> Start Recording </button>
    <button @click="stopRecording" v-if="isRecording" class="submit-button"> Stop Recording </button>

    <div v-if="isRecording" class = "output">
      <p> Recording in progress </p>
    </div>

    <div v-if="micPermissionStatus" class = "output">
      <p>{{ micPermissionStatus }} </p>
    </div>

    <div v-if="recordedAudioURL" class = "output">
      <p>Recording completed </p>
    </div>

    <div v-if="recordedAudioURL" class = "play-button">
      <button @click="playRecording" class="submit-button"> Play Recording </button>
      <button @click="transcribeRecording" class="submit-button"> Transcribe Recording </button>
    </div>

    <hr style="margin: 2rem 0" />

    <h1>Upload Audio File</h1>
    <input type="file" accept="audio/*" @change="onAudioFileChange" class="input-field" />
    <button @click="handleAudioUpload" class="submit-button">Upload Audio</button>

    <div v-if="audioUploadStatus" class="output">
      <p>{{ audioUploadStatus }}</p>
    </div>
  </div>
</template>

<style scoped>
.container {
  max-width: 600px;
  margin: 2rem auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  align-items: stretch;
}

.header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 60px;
  background-color: #35495e;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 1rem;
  box-sizing: border-box;
  color: white;
  z-index: 1000;
  gap: 100px;
}


.config-button {
  position: absolute;
  right: 1rem;
  padding: 0.5rem 1rem;
  background-color: #35495e;
  border: none;
  border-radius: 4px;
  color: white;
  cursor: pointer;
  z-index: 1001;
}

.config-button:hover {
  background-color: #2c3e50;
}

h2 {
  margin-bottom: 1rem;
  text-align: center;
}

.input-field {
  padding: 0.5rem;
  font-size: 1rem;
  margin-bottom: 1rem;
  border: 1px solid #ccc;
  border-radius: 4px;
}

.submit-button {
  padding: 0.75rem;
  font-size: 1rem;
  background-color: #42b983;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  margin-bottom: 1rem;
}

.submit-button:hover {
  background-color: #369f6e;
}

.play-button {
  display: flex;
  justify-content: center;
  margin-top: 1rem;
  gap: 25px
}

.output {
  padding: 1rem;
  background-color: #f9f9f9;
  border-radius: 4px;
  border: 1px solid #eee;
}
</style>
