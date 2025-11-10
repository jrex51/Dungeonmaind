import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import * as api from '@/api/playersAPI.ts';
import type { PlayerOut, Role, Hp, AbilityScores } from '@/api/playersAPI.ts';

export const useSessionStore = defineStore('session', () => {
  /* State */
  const currentPlayer = ref<PlayerOut | null>(hydratePlayer());
  const players = ref<PlayerOut[]>([]);
  const backendUrl = ref<string | null>(hydrateBackendUrl());

  async function join(name: string, role: Role, reuse_id?: string) {
    const p = await api.join(name, role, reuse_id);
    currentPlayer.value = p;
    persistPlayer(p);
    return p;
  }

  async function loadPlayers() {
    const list = await api.listPlayers();
    players.value = list;
    syncCurrentFromList(list);
  }

  function setCurrentPlayer(p: PlayerOut) {
    currentPlayer.value = p;
    persistPlayer(p);
  }

  async function leave() {
    if (!currentPlayer.value) return;
    try {
      await api.leave(currentPlayer.value.id);
    } finally {
      clearSession()
    }
  }

  function setBackendUrl(url: string) {
    backendUrl.value = url;
    persistBackendUrl(url);
  }
  function setLocalNetworkIP(ip: string) {
    if (ip === "") {
      localNetworkIP.value = null;
    } else {
      localNetworkIP.value = ip;
    }

  persistLocalNetworkIP(ip);
  }


  /* WebSocket helpers */
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
  function patchPlayer(id: string, patch: PlayerUpsert) {
    const i = players.value.findIndex(p => p.id === id);
    if (i !== -1) {
      players.value[i] = mergePlayers(players.value[i], patch);
    }
  function persistBackendUrl(url: string) {
  localStorage.setItem("backendUrl", url);
  }
  function persistLocalNetworkIP(ip: string) {
  localStorage.setItem("localNetworkIP", ip);
  }

  function hydratePlayer(): PlayerOut | null {
    const raw = localStorage.getItem("player");
    if (!raw) return null;
    try { return JSON.parse(raw) as PlayerOut; } catch { return null;}
  }

  function hydrateBackendUrl(): string | null {
  const raw = localStorage.getItem("backendUrl");
  if (!raw) return null;
  return raw;
  }

  function hydrateLocalNetworkIP(): string | null {
    const raw = localStorage.getItem("localNetworkIP");
    if (!raw) return null;
    if (raw === "") {
      return null;
    } else {
      return raw;
    }
  }

  function clearSession() {
    currentPlayer.value = null;
    backendUrl.value = null;
    localNetworkIP.value = null;
    players.value = [];
    clearPersist();
  }
  function clearPersist() {
    localStorage.removeItem("player");
    localStorage.removeItem("backendUrl");
    localStorage.removeItem("localNetworkIP");
  }

  function patchPlayer(id: string, patch: Partial<Pick<PlayerOut, 'hp'|'max_hp'|'temp_hp'|'attributes'>>) {
    players.value = players.value.map((p): PlayerOut =>
      p.id === id ? ({ ...p, ...patch } as PlayerOut) : p
    );
    if (currentPlayer.value?.id === id) {
      currentPlayer.value = { ...(currentPlayer.value as PlayerOut), ...patch } as PlayerOut;
    }
  }

  function forceLogout() {
    currentPlayer.value = null;
    players.value = [];
    sessionStorage.removeItem('player');
  }

  return {
    currentPlayer,
    players,
    isLeader,
    backendUrl,
    join,
    loadPlayers,
    leave,
    patchPlayer,
    setBackendUrl,
    forceLogout,
    localNetworkIP,
    setLocalNetworkIP,
    clearSession,
    setCurrentPlayer,
        // ws helpers
    applyWsJoin,
    applyWsLeave,
    applyWsUpdate,
    patchPlayer,
  };
});
