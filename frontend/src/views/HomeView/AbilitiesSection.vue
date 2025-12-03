<script setup lang="ts">
import { ref, computed } from 'vue'
import { type PlayerOut, updateMaxHp, damagePlayer, healPlayer, patchPlayerAbility, kickPlayer } from '@/api/playersAPI.ts'
import { useSessionStore } from '@/stores/session.ts'
import { SERVER_CONFIG } from '@/config/config'

const store = useSessionStore()

function apiBase(): string {
  return store.backendUrl ?? SERVER_CONFIG.BASE_URL
}

/** Ability PATCH*/
const abilityBusy = ref<Record<string, boolean>>({})

/** Abilities */
type AbilitySpec = {
  key: 'str' | 'dex' | 'con' | 'int_' | 'wis' | 'cha'
  label: string
}
const ABILITIES: AbilitySpec[] = [
  { key: 'str', label: 'STR' },
  { key: 'dex', label: 'DEX' },
  { key: 'con', label: 'CON' },
  { key: 'int_', label: 'INT' },
  { key: 'wis', label: 'WIS' },
  { key: 'cha', label: 'CHA' },
]

function getAbilityData(p: any) {
  const ability = p?.abilities ?? {}
  return ABILITIES.map((spec) => {
    const score = typeof ability[spec.key] === 'number' ? ability[spec.key] : undefined
    const mod = score !== undefined ? Math.floor((score - 10) / 2) : undefined
    return { ...spec, score, mod }
  })
}

/** Ability change */
async function patchAbility(playerId: string, key: AbilitySpec['key'], value: number) {
  if (!playerId) return
  abilityBusy.value[key] = true
  try {
    await patchPlayerAbility(playerId, key, value, apiBase())
  } catch (e) {
    console.error('Ability PATCH failed:', e)
  } finally {
    abilityBusy.value[key] = false
  }
}

function incAbility(p: any, key: AbilitySpec['key']) {
  const current = Number(p?.abilities?.[key] ?? 0)
  patchAbility(p.id, key, current + 1)
}

function decAbility(p: any, key: AbilitySpec['key']) {
  const current = Number(p?.abilities?.[key] ?? 0)
  patchAbility(p.id, key, current - 1)
}

/** Visible players (for abilities): leader sees members (not self/other leaders); member sees self */
const visiblePlayers = computed(() => {
  const players = store.players ?? []
  if (store.isLeader) {
    const selfId = store.currentPlayer?.id
    return players.filter((p: any) => {
      const isSelf = selfId != null && p?.id === selfId
      const role = typeof p?.role === 'string' ? p.role.toLowerCase() : ''
      const isLeaderRole = role === 'leader'
      return !isSelf && !isLeaderRole
    })
  }
  return store.currentPlayer ? [store.currentPlayer] : []
})

/* Healthbar */
async function damage(playerId: string, amount: number) {
  try {
    await damagePlayer(playerId, amount, apiBase())
  } catch (e) {
    console.error('Damage failed:', e)
  }
}

async function heal(playerId: string, amount: number) {
  try {
    await healPlayer(playerId, amount, apiBase())
  } catch (e) {
    console.error('Heal failed:', e)
  }
}

function clamp(n: number, min: number, max: number) {
  return Math.min(max, Math.max(min, n))
}

function hpPct(p: any) {
  const max = Math.max(1, Number(p?.hp?.max ?? 0))
  const curr = clamp(Number(p?.hp?.current ?? 0), 0, max)
  return Math.round((curr / max) * 100)
}

function tempPct(p: any) {
  const max = Math.max(1, Number(p?.hp?.max ?? 0))
  const curr = clamp(Number(p?.hp?.current ?? 0), 0, max)
  const temp = Math.max(0, Number(p?.hp?.temp ?? 0))
  const total = Math.min(curr + temp, max)
  return Math.max(0, Math.round((total / max) * 100) - Math.round((curr / max) * 100))
}

function hpClass(p: any) {
  const pct = hpPct(p)
  if (pct <= 30) return 'is-low'
  if (pct <= 60) return 'is-mid'
  return 'is-high'
}

async function onMaxHpChange(player: PlayerOut, event: Event) {
  const input = event.target as HTMLInputElement
  const raw = parseInt(input.value, 10)

  // Basic guard on the client; backend will enforce too
  if (!Number.isFinite(raw) || raw < 1) {
    input.value = String(player.hp.max)
    return
  }

  // remember old hp value
  const oldMax = player.hp.max
  const oldCur = player.hp.current

  try {
    const updated = await updateMaxHp(player.id, raw, apiBase())

    const index = store.players.findIndex((p: PlayerOut) => p.id === updated.id)
    if (index !== -1) {
      store.players[index] = updated
    }

    // check for increase or decrease (new MaxHP - old MaxHP)
    const delta = updated.hp.max - oldMax

    // if maxhp increased than increase current HP
    if (delta > 0) {
      await heal(player.id, 1)
    }

    // if maxhp decreased than decrease current HP
    else if (delta < 0 && oldMax!= oldCur) { // avoid  additional damage if healthpoints were full
      await damage(player.id, 1)
    }
  } catch (err) {
    console.error(err)
    input.value = String(player.hp.max)
  }
}

/** Kick using X-Player-Id for leader auth */
async function kick(playerId: string) {
  const actorId = store.currentPlayer?.id
  if (!actorId) {
    console.warn('Kick attempted without current player')
    return
  }
  try {
    await kickPlayer(playerId, actorId, apiBase())
  } catch (e) {
    console.error('Kick failed:', e)
  }
}
</script>

<template>
  <section
    :class="[
      'abilities-section',
      'rail-panel',
      !store.isLeader ? 'abilities-section--member' : null,
    ]"
  >
    <h2 class="rail-title">
      {{ store.isLeader ? 'Player Overview' : 'Your Information' }}
    </h2>

    <div v-if="visiblePlayers.length" class="ability-list">
      <div
        v-for="p in visiblePlayers"
        :key="p.id ?? p.name ?? JSON.stringify(p)"
        class="ability-card"
      >
        <div class="ability-card__header" v-if="store.isLeader">
          <div class="ability-card__name">
            {{ p.name ?? 'Unnamed Player' }}
          </div>
        </div>
        <div class="section__label">Abilities:</div>
        <div class="ability-grid">
          <div v-for="a in getAbilityData(p)" :key="a.key" class="ability-box">
            <div class="ability-label">
              {{ a.label }}
            </div>
            <div class="ability-score">
              <span>{{ a.score ?? '—' }}</span>
            </div>
            <div
              v-if="store.isLeader || p.id === store.currentPlayer?.id"
              class="ability-controls"
            >
              <button
                class="ability-stepper submit-button"
                :disabled="abilityBusy[a.key]"
                @click="decAbility(p, a.key)"
                aria-label="decrease"
              >
                −
              </button>
              <button
                class="ability-stepper submit-button"
                :disabled="abilityBusy[a.key]"
                @click="incAbility(p, a.key)"
                aria-label="increase"
              >
                +
              </button>
            </div>
          </div>
        </div>

        <div class="healthbar" :class="hpClass(p)">
          <!-- Column 1: Label -->
          <div class="section__label">Hit Points:</div>

          <!-- Column 2: Progressbar -->
          <div
            class="healthbar__track"
            role="progressbar"
            :aria-valuemin="0"
            :aria-valuemax="p.hp.max"
            :aria-valuenow="p.hp.current"
            :aria-valuetext="`${p.hp.current}/${p.hp.max}${
              p.hp.temp ? ` (+${p.hp.temp})` : ''
            }`"
            :title="`HP ${p.hp.current}/${p.hp.max}${
              p.hp.temp ? ` (+${p.hp.temp} temp)` : ''
            }`"
          >
            <div class="healthbar__fill" :style="{ width: hpPct(p) + '%' }"></div>

            <div
              v-if="p.hp.temp"
              class="healthbar__temp"
              :style="{
                left: hpPct(p) + '%',
                width: tempPct(p) + '%',
              }"
            ></div>
          </div>

          <!-- Column 3: Numbers -->
          <div class="healthbar__numbers">
            {{ p.hp.current }} / {{ p.hp.max }}
            <span v-if="p.hp.temp"> (+{{ p.hp.temp }}) </span>
          </div>

          <!-- Column 4: Buttons -->
          <div
            class="healthbar__controls"
            v-if="store.isLeader || p.id === store.currentPlayer?.id"
          >
            <button
              class="ability-stepper submit-button"
              @click="damage(p.id, 1)"
              aria-label="take 1 damage"
            >
              −
            </button>
            <button class="ability-stepper submit-button" @click="heal(p.id, 1)" aria-label="heal 1 hp">
              +
            </button>
          </div>
        </div>

        <div class="hpmax-row">
          <label class="section__label" :for="'hpmax-' + p.id"> Maximum Hit Points: </label>
          <input
            :id="'hpmax-' + p.id"
            class="hpmax-input"
            type="number"
            min="1"
            :value="p.hp.max"
            @change="onMaxHpChange(p, $event)"
          />
        </div>
        <div class="leader__controls" v-if="store.isLeader">
          <button class="submit-button"
            v-if="store.isLeader && p.id !== store.currentPlayer?.id"
            @click="kick(p.id)"
          >
            Kick
          </button>
        </div>
      </div>
    </div>
    <p v-else class="output">No players found.</p>
  </section>
</template>


<style src="@/assets/styles.css"></style>
<style scoped>
/* Abilities */
.abilities-section {
  width: 100%;
  margin: 0;
}

.abilities-section--member {
  margin-top: 2rem;
}

.ability-list {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.75rem;
}

.ability-card {
  border: 1px solid #695710;
  border-radius: 10px;
  padding: 0.75rem 0.9rem 1rem;
  background: rgba(110, 97, 50, 0.25);
  position: relative;
}

.leader__controls {
  position: absolute;
  top: 0.5rem;
  right: 0.75rem;
}

.ability-card__header {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  margin-bottom: 0.75rem;
  color: #392401;
}

.ability-card__name {
  font-size: 1.25rem;
  font-weight: 800;
  line-height: 1.2;
  font-family: 'MedievalSharp', cursive;
  letter-spacing: 0.03em;
  color: #392401;
}

.ability-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 0.5rem;
}

.ability-box {
  text-align: center;
  border: 1px solid #695710;
  border-radius: 8px;
  padding: 0.5rem 0.4rem;
  background: #f1e6b4;
  color: #392401;
}

.ability-label {
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.03em;
  color: #6b5710;
}

.ability-score {
  font-size: 1.1rem;
  font-weight: 800;
  line-height: 1.3;
}

/* + / − controls */
.ability-controls {
  display: flex;
  gap: 0.4rem;
  justify-content: center;
  margin-top: 0.4rem;
}

.ability-stepper {
  padding: 0.2rem 0.5rem;
  line-height: 1;
  border: 1px solid #695710;
  border-radius: 6px;
  background: #b74d30;
  color: #fff;
  cursor: pointer;
  font-family: 'MedievalSharp', cursive;
}

.ability-stepper:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Label for ability and healthbar */
.section__label {
  font-weight: 800;
  letter-spacing: 0.03em;
  color: #392401;
  font-size: 1.05rem;
}

/* Healthbar */
.healthbar {
  border-top: 1px solid rgba(57, 36, 1, 0.4);
  padding-top: 1rem;
  margin-top: 1.5rem;
  display: grid;
  grid-template-columns: auto 1fr auto auto;
  gap: 0.5rem 0.75rem;
  align-items: center;
}

.healthbar__numbers {
  justify-self: end;
  font-weight: 700;
  color: #392401;
  font-size: 1rem;
}

.healthbar__track {
  position: relative;
  height: 14px;
  border-radius: 7px;
  background: rgba(0, 0, 0, 0.2);
  outline: 1px solid #695710;
  overflow: hidden;
}

.healthbar__fill,
.healthbar__temp {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  width: 0;
  transition: width 200ms ease;
}

/* Basis-HP-Farbe (ändert sich je nach Rest-Prozent) */
.healthbar__fill {
  background: linear-gradient(180deg, #5bb45b, #2f8f2f); /* high */
}

.healthbar.is-mid .healthbar__fill {
  background: linear-gradient(180deg, #d6b34c, #b98f1e); /* mid */
}

.healthbar.is-low .healthbar__fill {
  background: linear-gradient(180deg, #d6634c, #b91e1e); /* low */
}

.healthbar__controls {
  display: flex;
  gap: 0.4rem;
  justify-self: end;
}

.healthbar__controls .ability-stepper {
  padding: 0.2rem 0.5rem;
  line-height: 1;
  min-width: 2rem;
  text-align: center;
}

/* Maximum hit points setting */
.hpmax-row {
  margin-top: 1rem;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
  border-top: 1px solid rgba(57, 36, 1, 0.4);
  padding-top: 1rem;
}

.hpmax-input {
  width: 5rem;
  padding: 0.4rem 0.5rem;
  font-size: 1rem;
  line-height: 1.2;
  text-align: center;
  border: 1px solid #695710;
  border-radius: 6px;
  background: #f1e6b4;
  color: #392401;
  font-family: 'MedievalSharp', cursive;
  font-weight: 700;
}
</style>
