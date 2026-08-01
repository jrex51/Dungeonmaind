<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { fetchTimelineEvents, type TimelineEvent } from '@/api/timelineAPI'

const router = useRouter()

const timelineEvents = ref<TimelineEvent[]>([])
const isLoading = ref(true)
const errorMessage = ref('')

function pad(value: number): string {
  return String(value).padStart(2, '0')
}

function formatTimestamp(timestamp: number): string {
  if (!Number.isFinite(timestamp) || timestamp < 0) {
    return '00:00:00'
  }

  const totalSeconds = Math.floor(timestamp)
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60

  return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`
}

async function loadTimeline() {
  isLoading.value = true
  errorMessage.value = ''

  try {
    timelineEvents.value = await fetchTimelineEvents()
  } catch (error) {
    console.error('Failed to load timeline events:', error)
    errorMessage.value = 'Failed to load timeline events.'
  } finally {
    isLoading.value = false
  }
}

function goHome() {
  router.push({ name: 'home' })
}

onMounted(() => {
  void loadTimeline()
})
</script>

<template>
  <div class="timeline-page">
    <div class="timeline-panel rail-panel">
      <h1>Timeline</h1>

      <p class="timeline-subtitle secondary-medieval-text">
        Interactive timeline of transcript events
      </p>

      <div v-if="isLoading" class="timeline-state secondary-medieval-text">
        Loading timeline...
      </div>

      <div v-else-if="errorMessage" class="timeline-state timeline-state--error secondary-medieval-text">
        {{ errorMessage }}
      </div>

      <div
        v-else-if="!timelineEvents.length"
        class="timeline-state timeline-state--empty secondary-medieval-text"
      >
        No timeline events available.<br />
        Transcribe a session to generate timeline events.
      </div>

      <ul v-else class="timeline-list">
        <li v-for="event in timelineEvents" :key="`${event.timestamp}-${event.title}`" class="timeline-item">
          <div class="timeline-item__header">
            [{{ formatTimestamp(event.timestamp) }}] {{ event.title }}
          </div>
          <p class="timeline-item__description">{{ event.description }}</p>
        </li>
      </ul>

      <button class="goHome-button" @click="goHome">return</button>
    </div>
  </div>
</template>

<style src="@/assets/styles.css"></style>
<style scoped>
.timeline-page {
  min-height: 100vh;
  padding: 5rem 1rem 2rem;
  box-sizing: border-box;
}

.timeline-panel {
  max-width: 900px;
  margin: 0 auto;
}

.timeline-subtitle {
  margin-top: -0.5rem;
  text-align: center;
}

.timeline-state {
  margin-top: 1rem;
  padding: 1rem;
  background: rgba(110, 97, 50, 0.45);
  border: 1px solid rgba(57, 36, 1, 0.25);
  border-radius: 10px;
  text-align: center;
}

.timeline-state--error {
  color: #7c1d1d;
}

.timeline-state--empty {
  line-height: 1.6;
}

.timeline-list {
  list-style: none;
  margin: 1rem 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.timeline-item {
  padding: 0.9rem 1rem;
  border-radius: 10px;
  background: rgba(241, 230, 180, 0.75);
  border: 1px solid rgba(57, 36, 1, 0.25);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.12);
}

.timeline-item__header {
  font-family: 'MedievalSharp', cursive;
  font-weight: 700;
  color: #392401;
  margin-bottom: 0.4rem;
}

.timeline-item__description {
  margin: 0;
  color: #4c3e06;
  line-height: 1.5;
  font-family: 'MedievalSharp', cursive;
}

.goHome-button {
  padding: 0.7rem 1.4rem;
  background-color: rgba(53, 73, 94, 0.9);
  border: 1px solid #4a575e;
  border-radius: 4px;
  color: white;
  cursor: pointer;
  font-family: 'MedievalSharp', cursive;
  font-weight: normal;
  font-size: 0.9rem;
  transition: background-color 0.3s ease;
  margin-top: 1rem;
}

.goHome-button:hover {
  background-color: #4a575e;
}
</style>