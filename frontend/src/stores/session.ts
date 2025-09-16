import { defineStore } from 'pinia';
import { ref, computed } from 'vue'
import * as api from "@/api/players"; // join, listPlayers und leave Funktion
import type { PlayerOut, Role } from "@/api/players";

export const useSessionStore = defineStore("session", () => {
  const currentPlayer = ref<PlayerOut | null>(hydrate());
  const players = ref<PlayerOut[]>([]);
  const isLeader = computed(() => currentPlayer.value?.role === "leader");

  async function join(name: string, role: Role) {
    const p = await api.join(name, role);
    currentPlayer.value = p;
    persist(p);
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
      currentPlayer.value = null;
      players.value = [];
      clearPersist();
    }
  }

  function persist(p: PlayerOut) {
    sessionStorage.setItem("player", JSON.stringify(p));
  }

  function hydrate(): PlayerOut | null {
    const raw = sessionStorage.getItem("player");
    if (!raw) return null;
    try { return JSON.parse(raw) as PlayerOut; } catch { return null;}
  }

  function clearPersist() {
    sessionStorage.removeItem("player");
  }

  return { currentPlayer, players, isLeader, join, loadPlayers, leave }
})
