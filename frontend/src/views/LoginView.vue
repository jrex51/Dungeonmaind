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
const baseUrl = ref<string>("http://localhost:8000");
const status = ref<Status>("idle");
const message = ref<string>("");
const lastStatus = ref<number | null>(null);

type CheckResult = {
  ok: boolean;
  status?: number;
  error?: string;
};

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

async function onImport() {
  const res = await fetch(`${SERVER_CONFIG.BASE_URL}${SERVER_CONFIG.ENDPOINTS.IMPORT_SESSION}`)
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

    <form class="join-card" @submit="onSubmit">
      <!-- 1) Rolle auswählen-->
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

      <!-- 3) Beitreten -->
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
  margin-top: 1rem;
  padding: 0.5rem;
  font-size: 1rem;
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
</style>
