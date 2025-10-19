import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import * as api from '@/api/players';
import type { PlayerOut, Role } from '@/api/players';

export const useSessionStore = defineStore('session', () => {
  const currentPlayer = ref<PlayerOut | null>(hydratePlayer());
  const players = ref<PlayerOut[]>([]);
  const backendUrl = ref<string | null>(hydrateBackendUrl());
  const isLeader = computed(() => currentPlayer.value?.role === 'leader');

  // API actions
  async function join(name: string, role: Role) {
    const p = await api.join(name, role);
    currentPlayer.value = p;
    persistPlayer(p);
    return p;
  }

  async function loadPlayers() {
    const list = await api.listPlayers();
    players.value = list;
    // Sync currentPlayer from fresh list (fixes F5 stale abilities)
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

  //WebSocket helpers
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

  function applyWsUpdate(p: PlayerOut) {
    upsertPlayer(p);
    if (currentPlayer.value?.id === p.id) {
      currentPlayer.value = { ...currentPlayer.value, ...p };
      persistPlayer(currentPlayer.value);
    }
  }

  // internals
  function upsertPlayer(p: PlayerOut) {
    const i = players.value.findIndex(x => x.id === p.id);
    if (i === -1) players.value.push(p);
    else players.value[i] = { ...players.value[i], ...p };
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
  };
});
