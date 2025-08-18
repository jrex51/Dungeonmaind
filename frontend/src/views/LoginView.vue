<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { SERVER_CONFIG } from '@/config/config'
import type { Role } from "@/api/players";
import { useSessionStore } from '@/stores/session.ts'
import { setApiBaseFromInput, toOrigin } from '@/config/apiBase.ts'

const store = useSessionStore();
const router = useRouter();

// --- Logik für checkConnection ---

// const router = useRouter()
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

async function checkConnection(baseUrl: string, endpoint: string, timeoutMs = 5000): Promise<CheckResult> {
  const url = toOrigin(baseUrl, endpoint);
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
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

  const result = await checkConnection(baseUrl.value, SERVER_CONFIG.ENDPOINTS.CHECK_CONNECTION);

  if (result.ok) {
    setApiBaseFromInput(baseUrl.value);
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
  if (n.length === 0) return "Bitte einen Namen eintragen.";
  if (n.length < 2) return "Name muss mindestens 2 Zeichen haben."
  return "";
});

// Button nur aktiv, wenn alles ok
const canSubmit = computed(() => role.value !== null && nameError.value === "");

// Formular-Submit
async function onSubmit(e: Event) {
  e.preventDefault();  // Browser-Reload verhindern
  const result = await checkConnection(baseUrl.value, SERVER_CONFIG.ENDPOINTS.CHECK_CONNECTION);
  if (result.ok) setApiBaseFromInput(baseUrl.value);
  touched.value = true;

  if (!canSubmit.value ||!role.value) return;

  submitting.value = true;
  try {
    await store.join(playerName.value.trim(), role.value);
    await router.push({ name: "home" });
  } catch (err) {
    serverError.value = err instanceof Error ? err.message : String(err);
  } finally {
    submitting.value = false;
  }
}

</script>


<template>
  <div class="login-page">
    <h1>Login Page</h1>

    <div class="check-card">
      <label for="baseUrl">Backend-Adresse</label>
      <input
        id="baseUrl"
        v-model.trim="baseUrl"
        placeholder="z.B. http://localhost:8080"
        :disabled="status === 'checking'"
      />

      <button @click="onCheck" :disabled="!baseUrl || status === 'checking'">
        {{ status === 'checking' ? 'Prüfe...' : 'Verbindung prüfen' }}
      </button>

      <p v-if="status === 'ok'">Erreichbar{{ lastStatus ? ` (HTTP ${lastStatus})` : '' }}</p>
      <p v-else-if="status === 'error'">Nicht erreichbar: {{ message }}</p>
    </div>


    <hr style="margin: 1rem 0" />

    <form class="join-card" @submit="onSubmit">
      <!-- 1) Rolle auswählen-->
      <fieldset>
        <legend>Rolle wählen</legend>

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

        <p v-if="touched && !role" class="error">Bitte Rolle auswählen.</p>
      </fieldset>

      <!-- 2) Spielernamen -->
      <label for="playerName">Dein Name</label>
      <input
        id="playerName"
        type="text"
        v-model.trim="playerName"
        maxlength="20"
        placeholder="z.B. Alex"
        @blur="touched = true"
        autocomplete="name"
        />
      <p v-if="touched && nameError" class="error">{{ nameError }}</p>

      <!-- 3) Beitreten -->
      <button type="submit" :disabled="!canSubmit || submitting">
        {{ submitting ? "Beitreten ..." : "Beitreten" }}
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
  margin-top: 2rem;
  padding: 0.75rem 1.5rem;
  font-size: 1rem;
  background-color: #42b983;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.done-button:hover {
  background-color: #369f6e;
}
</style>
