<script setup lang="ts">
import QrcodeVue from 'qrcode.vue'
import { SERVER_CONFIG } from '@/config/config'
import { useSessionStore } from '@/stores/session.ts'

const store = useSessionStore()

const localNetworkIP = SERVER_CONFIG.LOCAL_NETWORK_IP
const port = window.location.port
</script>

<template>
<div v-if="store.isLeader" :class="['join-link', 'rail-panel']">
  <h2 class="rail-title">Join Link (New Members)</h2>
  <label>http://{{ localNetworkIP }}:{{ port }}</label>
  <div v-if="localNetworkIP" style="margin-top: 1rem;">
    <qrcode-vue
      :value="`http://${localNetworkIP}:${port}`"
      :size="180"
      level="M"
    />
    <p>Scan the code to open<br>
      Dungeonmaind on another device</p>
  </div>
</div>
</template>

<style src="@/assets/styles.css"></style>
<style scoped>

.join-link {
  font-family: 'MedievalSharp', cursive;
  font-weight: 600;
  font-size: 1.2rem;
  text-align: center;
}

label {
  font-weight: 600;
  font-size: 1.1rem;
  font-family: 'MedievalSharp', cursive;
}
</style>
