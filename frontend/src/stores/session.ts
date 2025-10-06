import { defineStore } from 'pinia';
import { ref, computed } from 'vue'
import * as api from "@/api/players"; // join, listPlayers und leave Funktion
import type { PlayerOut, Role } from "@/api/players";

export const useSessionStore = defineStore("session", () => {
  const currentPlayer = ref<PlayerOut | null>(hydratePlayer());
  const players = ref<PlayerOut[]>([]);
  const isLeader = computed(() => currentPlayer.value?.role === "leader");
  const backendUrl = ref<string | null>(hydrateBackendUrl());

  async function join(name: string, role: Role) {
    const p = await api.join(name, role);
    currentPlayer.value = p;
    persistPlayer(p);
    return p;
  }

  async function loadPlayers() {
    players.value = await api.listPlayers();
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

  function persistPlayer(p: PlayerOut) {
    localStorage.setItem("player", JSON.stringify(p));
  }
  function persistBackendUrl(url: string) {
  localStorage.setItem("backendUrl", url);
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
  function clearSession() {
    currentPlayer.value = null;
    backendUrl.value = null;
    players.value = [];
    clearPersist();
  }
  function clearPersist() {
    localStorage.removeItem("player");
    localStorage.removeItem("backendUrl");
  }

  return { currentPlayer, players, isLeader, backendUrl, setBackendUrl, join, loadPlayers, leave, clearSession }
})
