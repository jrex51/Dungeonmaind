import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import * as api from '@/api/players';
import type { PlayerOut, Role, Hp, AbilityScores } from '@/api/players';

export const useSessionStore = defineStore('session', () => {
  /* ========================
   * State
   * ====================== */
  const currentPlayer = ref<PlayerOut | null>(hydratePlayer());
  const players = ref<PlayerOut[]>([]);
  const backendUrl = ref<string | null>(hydrateBackendUrl());

  /* ========================
   * Getters
   * ====================== */
  const isLeader = computed(() => currentPlayer.value?.role === 'leader');

  /* ========================
   * Types (for WS/patch upserts)
   * ====================== */
  type PlayerUpsert =
    Partial<Omit<PlayerOut, 'hp' | 'abilities'>> & {
    hp?: Partial<Hp>;
    abilities?: Partial<AbilityScores> | Record<string, unknown>;
  };

  type PlayerPatch = PlayerUpsert;

  /* ========================
   * Internal helpers
   * ====================== */
  // Deep-merge hp and abilities; shallow-merge everything else
  function mergePlayers(base: PlayerOut, incoming: PlayerUpsert): PlayerOut {
    return {
      ...base,
      ...incoming,
      hp: incoming.hp ? { ...base.hp, ...incoming.hp } : base.hp,
      abilities: incoming.abilities
        ? { ...(base.abilities ?? {}), ...(incoming.abilities as Record<string, unknown>) }
        : base.abilities,
    };
  }

  function upsertPlayer(p: PlayerOut) {
    const i = players.value.findIndex(x => x.id === p.id);
    if (i === -1) players.value.push(p);
    else players.value[i] = mergePlayers(players.value[i], p);
  }

  function syncCurrentFromList(list: PlayerOut[]) {
    const id = currentPlayer.value?.id;
    if (!id) return;
    const fresh = list.find(p => p.id === id);
    if (fresh) {
      currentPlayer.value = fresh;
      persistPlayer(fresh);
    }
  }

  function persistPlayer(p: PlayerOut | null) {
    try {
      if (p) localStorage.setItem('player', JSON.stringify(p));
      else localStorage.removeItem('player');
    } catch {}
  }

  function removePersistedPlayer() {
    try { localStorage.removeItem('player'); } catch {}
  }

  function persistBackendUrl(url: string) {
    try { localStorage.setItem('backendUrl', url); } catch {}
  }

  function hydratePlayer(): PlayerOut | null {
    try {
      const raw = localStorage.getItem('player');
      return raw ? (JSON.parse(raw) as PlayerOut) : null;
    } catch { return null; }
  }

  function hydrateBackendUrl(): string | null {
    try { return localStorage.getItem('backendUrl'); } catch { return null; }
  }

  function clearPersist() {
    removePersistedPlayer();
    try { localStorage.removeItem('backendUrl'); } catch {}
  }

  /* ========================
   * API actions
   * ====================== */
  async function join(name: string, role: Role) {
    const p = await api.join(name, role);
    currentPlayer.value = p;
    persistPlayer(p);
    return p;
  }

  async function loadPlayers() {
    const list = await api.listPlayers();
    players.value = list;
    syncCurrentFromList(list);
  }

  async function leave() {
    if (!currentPlayer.value) return;
    try {
      await api.leave(currentPlayer.value.id);
    } finally {
      currentPlayer.value = null;
      players.value = [];
      clearPersist();
    }
  }

  function setBackendUrl(url: string) {
    backendUrl.value = url;
    persistBackendUrl(url);
  }

  /* ========================
   * WebSocket helpers
   * ====================== */
  function applyWsJoin(p: PlayerOut) {
    upsertPlayer(p);
  }

  function applyWsLeave(id: string) {
    players.value = players.value.filter(pl => pl.id !== id);
    if (currentPlayer.value?.id === id) {
      currentPlayer.value = null;
      removePersistedPlayer();
    }
  }

  // Accept full or partial updates; if partial, we merge into existing
  function applyWsUpdate(p: PlayerOut) {
    upsertPlayer(p);
    if (currentPlayer.value?.id === p.id) {
      currentPlayer.value = mergePlayers(currentPlayer.value, p);
      persistPlayer(currentPlayer.value);
    }
  }

  // Patch helper used by granular WS events (hp/abilities)
  function patchPlayer(id: string, patch: PlayerPatch) {
    const i = players.value.findIndex(p => p.id === id);
    if (i !== -1) {
      players.value[i] = mergePlayers(players.value[i], patch);
    }
    if (currentPlayer.value?.id === id) {
      currentPlayer.value = mergePlayers(currentPlayer.value, patch);
      persistPlayer(currentPlayer.value);
    }
  }

  /* ========================
   * Expose store
   * ====================== */
  return {
    // state
    currentPlayer,
    players,
    backendUrl,
    // getters
    isLeader,
    // actions
    join,
    loadPlayers,
    leave,
    setBackendUrl,
    // ws helpers
    applyWsJoin,
    applyWsLeave,
    applyWsUpdate,
    patchPlayer,
  };
});
