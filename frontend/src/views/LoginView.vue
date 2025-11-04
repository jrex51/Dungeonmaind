<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { SERVER_CONFIG } from '@/config/config'
import type { Role } from "@/api/playersAPI.ts";
import { useSessionStore } from '@/stores/session.ts'

const store = useSessionStore();
const router = useRouter();

// --- Logik für checkConnection ---

type Status = "idle" | "checking" | "ok" | "error";

// checkConnection
const baseUrl = ref<string>(`http://${window.location.hostname}:8000`);
const status = ref<Status>("idle");
const message = ref<string>("");
const lastStatus = ref<number | null>(null);

const networkIPs = __NETWORK_IPS__
const selectedNetworkIP = ref(networkIPs[0] || "")

type CheckResult = {
  ok: boolean;
  status?: number;
  error?: string;
};

// For session import
const showImportModal = ref(false)
const sessions = ref([])
const selectedSession = ref("")

async function checkConnection(backendUrl: string, timeoutMs = 5000): Promise<CheckResult> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(`${backendUrl}${SERVER_CONFIG.ENDPOINTS.CHECK_CONNECTION}`, {
      method: "GET",
      signal: controller.signal,
      });
    // response.ok == Status 200 (und auch 204)
    return { ok: response.ok, status: response.status };
  } catch (err: unknown) {
    // AbortError unterscheidbar von echten Netzwerkfehlern
    const msg = err instanceof Error ? err.message : String(err);
    return { ok: false, error: msg };
  } finally {
    clearTimeout(timeoutId);
  }
}

async function onCheck() {
  status.value = "checking";
  message.value = "";
  lastStatus.value = null;

  const backendUrl = normalizeOrigin(baseUrl.value)
  const result = await checkConnection(backendUrl);

  if (result.ok) {
    status.value = "ok";
    lastStatus.value = result.status ?? null;
  } else {
    status.value = "error";
    message.value = result.error ?? `HTTP ${result.status ?? "?"}`;
  }
}

// --- Logik für Gruppe ---

// Zustand (reaktiv)
const role = ref<Role | null>(null);  // null = noch nichts gewählt
const playerName = ref<string>("");   // Eingabetext
const submitting = ref(false);        // Button-Loading-Status
const touched = ref(false);           // für einfache Fehlermeldungs-Steuerung
const serverError = ref("");

// einfache Validierung für den Namen
const nameError = computed(() => {
  const n = playerName.value.trim();
  if (n.length === 0) return "Please enter a name.";
  if (n.length < 2) return "Your name must be at least 2 characters."
  return "";
});

// Button nur aktiv, wenn alles ok
const canSubmit = computed(() => role.value !== null && nameError.value === "");


// Formular-Submit
async function onSubmit(e: Event) {
  e.preventDefault();  // Browser-Reload verhindern
  const backendUrl = normalizeOrigin(baseUrl.value)
  const result = await checkConnection(backendUrl);
  if (result.ok) store.setBackendUrl(backendUrl);
  touched.value = true;

  if (!canSubmit.value || !role.value) return;

  submitting.value = true;
  try {
    await store.join(playerName.value.trim(), role.value);
    store.setLocalNetworkIP(selectedNetworkIP.value)
    await router.push({ name: "home" });
  } catch (err: any) {
    console.error("Join error:", err);

  if (err?.response) {
    // Axios-Format
    const data = err.response.data;
    serverError.value =
      typeof data === "object" && data.detail
        ? data.detail
        : JSON.stringify(data);
  } else if (err instanceof Error) {
    try {
      // versuchen JSON aus err.message zu parsen
      const data = JSON.parse(err.message);
      serverError.value =
        typeof data === "object" && data.detail
          ? data.detail
          : err.message;
    } catch {
      // fallback: plain Error message
      serverError.value = err.message;
    }
    } else {
      serverError.value = String(err);
    }
  } finally {
    submitting.value = false;
  }
}

function normalizeOrigin(input: string): string {
  // Protokoll sicherstellen (http/https) oder protokoll-relative //host zulassen
  const withProtocol = /^(https?:)?\/\//i.test(input) ? input : `http://${input}`;
  // Nur die Origin verwenden (Schema + Host + Port), Pfade abschneiden
  //    (damit "http://host:8000/health" -> "http://host:8000")
  return new URL(withProtocol).origin;
}


async function confirmImport() {
  if (!selectedSession.value) return

  try {
    const res = await fetch(`${SERVER_CONFIG.BASE_URL}${SERVER_CONFIG.ENDPOINTS.IMPORT_SESSION}`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        session_name: selectedSession.value,
      }),
    })
    if (!res.ok) throw new Error("Import failed")
      const leader = await res.json();

    if (!leader) throw new Error("No leader returned from backend");

    store.setCurrentPlayer(leader);

    await router.push({ name: "home" });
    showImportModal.value = false
    alert(`Session "${selectedSession.value}" imported successfully!`)
  } catch (err) {
    console.error(err);
    if (err instanceof Error) {
      alert("Import failed: " + err.message);
    } else {
      alert("Import failed: " + String(err));
    }
  }
}

async function onImport() {
  try {
    const res = await fetch(`${SERVER_CONFIG.BASE_URL}${SERVER_CONFIG.ENDPOINTS.GET_SESSIONS}`)
    if (!res.ok) throw new Error("Failed to fetch sessions")

    const data = await res.json()
    sessions.value = data.folders
    showImportModal.value = true
  } catch (err) {
    console.error(err)
  }
}


</script>


<template>
  <div class="login-page">
    <h1>Login Page</h1>

    <div class="check-card">
      <label for="baseUrl">Backend-Adresse</label>
      <input
        class = "input-field"
        id="baseUrl"
        v-model.trim="baseUrl"
        placeholder="z.B. http://localhost:8080"
        :disabled="status === 'checking'"
      />

      <button class="done-button" @click="onCheck" :disabled="!baseUrl || status === 'checking'">
        {{ status === 'checking' ? 'Checking...' : 'Check connection' }}
      </button>

      <p v-if="status === 'ok'">Erreichbar{{ lastStatus ? ` (HTTP ${lastStatus})` : '' }}</p>
      <p v-else-if="status === 'error'">Not available: {{ message }}</p>
    </div>


    <hr style="margin: 1rem 0" />

    <div>
      <button class="done-button" @click="onImport">Import Session</button>
    </div>
    <div v-if="showImportModal" class="modal-overlay">
      <div class="modal">
        <h2>Select a session to import</h2>

        <div class="session-list">
          <div
            v-for="(folder, index) in sessions"
            :key="index"
            class="session-item"
            :class="{ selected: selectedSession === folder }"
            @click="selectedSession = folder"
          >
            {{ folder }}
          </div>
        </div>

        <div class="modal-buttons">
          <button class="btn-cancel" @click="showImportModal = false">Cancel</button>
          <button class="btn-save" :disabled="!selectedSession" @click="confirmImport">
            Import
          </button>
        </div>
      </div>
    </div>

    <form class="join-card" @submit="onSubmit">
      <!-- 1) select role-->
      <fieldset>
        <legend>Choose a role</legend>

        <label>
          <input
            type="radio"
            name="role"
            :value="'leader'"
            v-model="role"
            />
          Leader
        </label>

        <label>
          <input
            type="radio"
            name="role"
            :value="'member'"
            v-model="role"
            />
          Member
        </label>

        <p v-if="touched && !role" class="error">Please select a role.</p>
      </fieldset>

      <!-- 2) local network IP -->
      <div v-if="role === 'leader'">
        <div style="margin-top: 4px;"></div>
        <div v-if="networkIPs.length > 1">
        <label for="networkIP">Select your local network IP:</label>
        <div style="margin-top: 1px;"></div>
        <select id="networkIP" v-model="selectedNetworkIP">
          <option v-for="networkIP in networkIPs" :key="networkIP" :value="networkIP">
            {{ networkIP }}
          </option>
        </select>
        </div>
        <div v-else>
          <label for="networkIP">Enter your local network IP:</label>
          <div style="margin-top: 1px;"></div>
          <input
            id="networkIP"
            type="text"
            v-model="selectedNetworkIP"
            placeholder="e.g. FRITZ!Box: 192.168.178.x"
            style="width: 100%; max-width: 200px;"
          />
        </div>
      </div>

      <!-- 3) player name -->
      <div style="margin-top: 4px;"></div>
      <!-- 2) Spielernamen -->
      <label for="playerName">Your Name</label>
      <input
        class = "input-field"
        id="playerName"
        type="text"
        v-model.trim="playerName"
        maxlength="20"
        placeholder="z.B. Alex"
        @blur="touched = true"
        autocomplete="name"
        />
      <p v-if="touched && nameError" class="error">{{ nameError }}</p>
      <p v-if="serverError" class="error">{{ serverError }}</p>

      <!-- 4) join -->
      <button class="done-button" type="submit" :disabled="!canSubmit || submitting">
        {{ submitting ? "Join ..." : "Join" }}
      </button>
    </form>
  </div>
</template>

<style scoped>
.config-page {
  max-width: 600px;
  margin: 2rem auto;
  padding: 1rem;
  text-align: center;
}

select {

  padding: 0.5rem;
  font-size: 0.9rem;
}

.done-button {
  padding: 0.5rem 1rem;
  background-color: rgba(53, 73, 94, 0.9);
  border: 1px solid #4a575e;
  border-radius: 4px;
  color: white;
  cursor: pointer;
  font-family: 'MedievalSharp', cursive;
  font-weight: normal;
  transition: background-color 0.3s ease;
}

.done-button :hover {
  background-color: #4a575e;
}

.input-field {
  padding: 0.75rem;
  font-size: 1rem;
  margin-bottom: 1rem;
  border: 1px solid #695710;
  border-radius: 10px;
  font-family: 'MedievalSharp', cursive;
  font-weight: bolder;
  background-color: #f1e6b4;

  color: #4c3e06;
  width: 90%;
  box-sizing: border-box;
}

.login-page,
.login-page h1,
.login-page p,
.login-page label,
.login-page fieldset,
.login-page legend,
.login-page button {
  font-family: 'MedievalSharp', cursive;
}

.login-page input,
.login-page textarea,
.login-page select {
  font-family: inherit;
}

/* Modal base */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 9999;
}

.modal {
  background: rgba(163, 148, 95, 0.8);
  border-radius: 12px;
  padding: 24px;
  width: 340px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
  text-align: center;
  color: #000;
}

.modal h2 {
  font-size: 1.2rem;
  font-weight: 600;
  margin-bottom: 1rem;
}

/* Session list */
.session-list {
  max-height: 220px;
  overflow-y: auto;
  border: 1px solid #ddd;
  border-radius: 6px;
  margin-bottom: 1rem;
  padding: 4px;
}

.session-item {
  padding: 8px 10px;
  border-radius: 4px;
  text-align: left;
  cursor: pointer;
  transition: background 0.2s ease;
}

.session-item:hover {
  background: #f3f4f6; /* gray-100 */
}

.session-item.selected {
  background: #2563eb; /* blue-600 */
  color: white;
}

/* Buttons */
.modal-buttons {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.btn-cancel,
.btn-save {
  padding: 6px 12px;
  border-radius: 6px;
  border: none;
  cursor: pointer;
  font-weight: 500;
  transition: background 0.2s ease;
}

.btn-cancel {
  background: #ddd;
}

.btn-cancel:hover {
  background: #ccc;
}

.btn-save {
  background: #4a575e;
  color: white;
}

.btn-save:hover {
  background: #1d4ed8;
}

.btn-save:disabled {
  background: #9ca3af;
  cursor: not-allowed;
}
</style>
