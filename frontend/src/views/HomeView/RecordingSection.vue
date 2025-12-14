<script setup lang="ts">
import { useRecorderStore } from '@/stores/recorder.ts'

/** Holds recording section */


const recorder = useRecorderStore()

async function startRecording() {
  await recorder.startRecording()
}

function stopRecording() {
  recorder.stopRecording()
}

function playRecording() {
  recorder.playRecording()
}
</script>

<template>
  <div class="content-section">
    <h2>Record Using Microphone</h2>

    <!-- Leader-only: recording -->
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
</template>

<style src="@/assets/styles.css"></style>
<style scoped>
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
</style>
