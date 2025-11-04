<script setup lang="ts">
import { ref, watch } from 'vue'
import {useRouter} from "vue-router";
import QrcodeVue from 'qrcode.vue'
import { SERVER_CONFIG } from '@/config/config'

const router = useRouter()
const localNetworkIP = SERVER_CONFIG.LOCAL_NETWORK_IP

const port = window.location.port

const url = ""

function goHome() {
  router.push('/')
}

function done() {
  goHome()
}



</script>

<template>
  <div class="container">
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

    <hr style="margin: 1rem 0" />

    <button @click="done" class="done-button">Done</button>
  </div>
</template>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=MedievalSharp&display=swap');

.container {
  max-width: 600px;
  margin: 80px auto 2rem auto; /* leave room for header */
  padding: 2rem;
  background-color: rgba(163, 148, 95, 0.8); /* parchment look */
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  font-family: 'MedievalSharp', cursive;
  font-weight: 600;
  font-size: 1.2rem;
  color: #392401;
  text-align: center;
  box-sizing: border-box;
}

label,
option {
  font-weight: 600;
  font-size: 1.1rem;
  font-family: 'MedievalSharp', cursive;
}

select {
  padding: 0.75rem;
  font-family: 'MedievalSharp', cursive;
  font-weight: 600;
  font-size: 1.1rem;
  width: 200px;
  border-radius: 10px;
  border: 1px solid #695710;
  background-color: #f1e6b4;
  color: #4c3e06;
  box-sizing: border-box;
}

.done-button {
  margin-top: 2rem;
  padding: 0.75rem 1.5rem;
  font-family: 'MedievalSharp';
  font-weight: bold;
  font-weight: 400;
  font-size: 1rem;
  background-color: #b74d30;
  color: white;
  border: 1px solid #8e7513;
  border-radius: 10px;
  cursor: pointer;

}

.done-button:hover {
  background-color: #7e6f34;
}
</style>
