<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { SERVER_CONFIG } from '@/config/config'
import type { PlayerOut, Role } from '@/api/players'
import { useSessionStore } from '@/stores/session.ts'

const store = useSessionStore();
const router = useRouter();

// Logik für checkConnection

type Status = "idle" | "checking" | "ok" | "error";

// Typen für den Check
type JoinCheckStatus = 'available' | 'inactive_match' | 'active_conflict';
type JoinCheckOut = {
  status: JoinCheckStatus;
  candidate?: PlayerOut;
}

async function preflightAndJoin(backendUrl: string, name: string, role: Role) {
  // 1) Preflight-Check
  console.debug(`preflightAndJoin: versuche mit ${name} zu joinen`);
  const checkUrl = new URL('/players/join/check', backendUrl);
  checkUrl.searchParams.set('name', name);
  const res = await fetch(checkUrl.toString(), { credentials: 'include' });
  if (!res.ok) {
    throw new Error(JSON.stringify({ detail: `Join-Check fehlgeschlagen (${res.status}` }));
  }
  const check: JoinCheckOut = await res.json();

  if (check.status === 'available') {
    // normaler Join
    console.debug(`preflightAndJoin: ${name} ist verfügbar`);
    await store.join(name, role);
    return;
  }

  if (check.status === 'active_conflict') {
    console.debug(`preflightAndJoin: es gibt einen aktiven Spieler mit dem namen`);
    // Name schon bei einem aktiven Spieler belegt
    throw new Error(JSON.stringify({ detail: `Der Name "${name}" ist bereits vergeben.` }));
  }

  if (check.status === 'inactive_match' && check.candidate) {
    // Nutzer fragen: alten Spieler reaktivieren?
    console.debug(`preflightAndJoin: inaktiven Spieler mit dem Namen gefunden`);
    const reuse = window.confirm(
      `Es gibt einen inaktiven Spieler "${check.candidate.name}". ` +
      `Möchtest du diesen wiederverwenden (HP/Attribute bleiben erhalten)?`
    );
    if (reuse) {
      // Reuse-Join
      console.debug(`preflightAndJoin: Spieler wird reaktiviert`);
      await store.join(name, role, check.candidate.id);
      return;
    } else {
      // neuer Spieler mit gleichem Namen ist erlaubt (nur aktive Namen sind geblockt)
      console.debug(`preflightAndJoin: Spieler wird neu angelegt`);
      await store.join(name, role);
      return;
    }
  }

  // sollte nie passieren
  await store.join(name, role);
}

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
    await preflightAndJoin(backendUrl, playerName.value.trim(), role.value);
    await router.push({ name: "home" });
  } catch (err: any) {
    console.error("Join error:", err);

  // Fehler auslesen
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
      <p v-if="serverError" class="error">{{ serverError }}</p>

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
