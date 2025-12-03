<script setup lang="ts">
import { ref } from 'vue'
import { useSessionStore } from '@/stores/session.ts'

const store = useSessionStore()

/** Dice */
const diceResult = ref<string>('')

/** Dice */
function rollDice(sides: number) {
  const result = Math.floor(Math.random() * sides) + 1
  diceResult.value = `W${sides} → ${result}`
}
</script>

<template>
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
</template>

<style src="@/assets/styles.css"></style>
<style scoped>
/* Dice */
.dice-widget {
  position: static;
  width: 100%;
  margin-top: 0rem;
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
</style>
