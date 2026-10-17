# Simple Docker commands

Run in PowerShell from the project folder. Docker Desktop must be running and `backend/.env` must exist.

## 1. Normal use — same project folder

**First build and start everything:**

```powershell
docker compose -f dockerCompose.yml -f dockerCompose.gpu.yml up -d --build
```

**Up — use existing images:**

```powershell
docker compose -f dockerCompose.yml -f dockerCompose.gpu.yml up -d --no-build
```

**Down — keep images and saved models:**

```powershell
docker compose -f dockerCompose.yml -f dockerCompose.gpu.yml down
```

**Rebuild backend/frontend only — leave Ollama untouched:**

```powershell
docker compose -f dockerCompose.yml -f dockerCompose.gpu.yml up -d --no-deps --build --renew-anon-volumes backend frontend
```

Ollama must already be running. After `down`, run the Up command first.

## 2. Reuse existing images — another project folder

Replace `"<existing-project-name>"` with your old Compose project name, not a full image name. Keep the same service names and saved model-volume mounts in the new folder.

**Turn up the existing ollama first:**

```PowerShell
docker compose -p "<existing-project-name>" -f dockerCompose.yml -f dockerCompose.gpu.yml up -d --no-deps --build ollama
```

docker compose -p "<existing-project-name></existing>" -f dockerCompose.yml -f dockerCompose.gpu.yml up -d --no-deps --build olllama

**Rebuild new backend/frontend code — leave Ollama untouched**

```powershell
docker compose -p "<existing-project-name>" -f dockerCompose.yml -f dockerCompose.gpu.yml up -d --no-deps --build --renew-anon-volumes backend frontend
```

**Up — start everything using existing images:**

```powershell
docker compose -p "<existing-project-name>" -f dockerCompose.yml -f dockerCompose.gpu.yml up -d --no-build
```

**Down — keep images and saved models:**

```powershell
docker compose -p "<existing-project-name>" -f dockerCompose.yml -f dockerCompose.gpu.yml down
```

Run Up first so Ollama is running, then Rebuild. Compatible cached layers and saved models are reused; missing packages/models may still download.

Normal Python/frontend code edits just need saving while containers are running. Do not add `-v` to Down if you want to keep saved models.
