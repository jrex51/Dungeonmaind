<script setup lang="ts">
import { useSessionStore } from '@/stores/session.ts'
import { useRouter } from 'vue-router'
import { useRecorderStore } from '@/stores/recorder.ts'

/** Holds Greeter, Player list and Leave action */

const store = useSessionStore()
const router = useRouter()
const recorder = useRecorderStore()

/** Session actions */
async function onLeave() {
  recorder.stopRecording() //stop recording when leaving session
  await store.leave()
  await router.push({ name: 'login' })
}
</script>

<template>
  <section>
    <h2>Hello {{ store.currentPlayer?.name }}</h2>
    <p v-if="store.isLeader" class="secondary-medieval-text">
      You are the Leader.
    </p>

    <button class="submit-button" @click="onLeave">Leave</button>

    <h3 class="secondary-medieval-text">Players</h3>
    <ul>
      <li
        v-for="p in store.players"
        :key="p.id"
        class="secondary-medieval-text"
      >
        {{ p.name }} ({{ p.role }})
      </li>
    </ul>
  </section>
</template>

<style src="@/assets/styles.css"></style>
