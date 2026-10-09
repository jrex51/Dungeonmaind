# Fast Docker development

Run these commands from the repository root. This project uses the nonstandard
filename `dockerCompose.yml`, so always pass `-f dockerCompose.yml`.
Keep Docker's BuildKit enabled (the Dockerfile uses cache mounts).

## Daily commands

```sh
# Initial setup, or intentionally build all services after broad image changes:
docker compose -f dockerCompose.yml up -d --build

# Later starts: reuse images. This also starts Ollama if needed.
docker compose -f dockerCompose.yml up -d backend

# Normal Python edits: just save the file. No Docker command is needed.
# ./backend is mounted at /app; the existing uvicorn --reload restarts Python.
docker compose -f dockerCompose.yml logs -f backend

# Application dependencies: edit backend/requirements.txt, then:
# --no-deps assumes Ollama is already running; unrelated containers stay running.
docker compose -f dockerCompose.yml up -d --no-deps --build backend

# ML/audio dependencies: edit backend/requirements-ml.txt, then use the same
# backend-only command above. Expect ML installation/model layers to rebuild.

# Frontend dependencies: edit package.json/package-lock.json, then:
# Refresh its anonymous /app/node_modules volume to use the new image packages.
docker compose -f dockerCompose.yml up -d --no-deps --build --renew-anon-volumes frontend

# Ollama Dockerfile or model pull list changes only:
docker compose -f dockerCompose.yml up -d --no-deps --build ollama

# Pause the stack without removing containers or model caches:
docker compose -f dockerCompose.yml stop
```

For GPU mode append `-f dockerCompose.gpu.yml` after the base `-f` in each
command. Likewise retain `-f dockerCompose.map.yml` when using the map override.
Normal frontend source edits also use the existing bind mount and Vite server.
Use an all-service build only for initial setup or intentional changes across
services; `down` followed by `up --build` is unnecessary for dependency edits.

## Why the old build was expensive

| Change | Old invalidation | New invalidation |
| --- | --- | --- |
| Python source, ordinary development | Already bind-mounted with reload; no build needed | Same, no pip or model download steps |
| Python source, if explicitly rebuilt | `COPY app` and every later layer, including all three model downloads | Only final `COPY app` and image metadata |
| `requirements.txt` | pip/wheel upgrade, whole dependency install, CTranslate2 replacement, PyTorch uninstall/reinstall, CUDA libraries, source, all model downloads | Late application pip layer, final source copy and image metadata |
| `requirements-ml.txt` | Previously part of the single requirements file | ML pip install and later layers; earlier CUDA wheel install stays cached |
| Dockerfile | First changed instruction and its descendants; not automatically every instruction | Same Docker rule; late edits retain expensive earlier layers |

The old dependency install could download PyTorch through WhisperX and then
uninstall it to install the CUDA distribution. Every `--no-cache-dir` install
discarded useful pip downloads. Now the intended CUDA 12.6 wheels are installed
first; stable ML packages reuse them. All pip steps use a BuildKit cache mount
at `/root/.cache/pip`, outside the final image. The application install consumes
the complete requirements list and ML constraints, reusing satisfied installed
packages, then runs `pip check`. The original direct dependency versions and
intended CUDA/Whisper runtime versions are retained.

Models are downloaded before application dependencies and source. Thus ordinary
application dependency edits preserve the SentenceTransformer, WhisperX ASR and
English alignment model layers. Source remains in the image for standalone use.
The Compose source mount and reload command are unchanged.

## Model persistence and remaining costs

`backend_models` mounts `/models` (SentenceTransformer, WhisperX, Torch) and
`backend_huggingface` mounts `/root/.cache/huggingface` (including runtime
diarization downloads). Docker seeds **new empty** named volumes with the image's
existing directory contents. They survive container recreation. An existing
volume is not refreshed from a newer image; newly selected models can still
download once at runtime. Keep these volumes when stopping/recreating services.
BuildKit pip downloads and runtime model volumes are separate caches.

Ollama already has `ollama_volume:/root/.ollama`; it is retained unchanged. Its
Dockerfile runs `run-ollama.sh` during **build**, including a fixed 10-second wait
and two model pulls. These rerun when that script, its preceding layers or base
image change, or build cache is unavailable. They are not normal container startup
commands. Backend-only builds never build Ollama or frontend. Existing Ollama
volumes retain their existing models even when the image pull list changes;
updating that list does not update an already populated runtime volume.

The frontend already caches `npm ci` behind `COPY package*.json`. Its development
Compose target still runs `npm run build` during image builds; source changes in
normal development require no build. No frontend image or application behavior
was changed here.

The largest expected cold-build costs are CUDA PyTorch wheels and their NVIDIA
libraries, the ML dependency install, and model downloads. Actual timings have
not been measured in this workspace. A cold build or stable ML dependency change
can still take many minutes. Cache reuse requires the same builder/platform and
retained build cache; unpinned transitive dependencies remain as in the existing
project, so an application dependency can still require additional packages.

Reload still imports WhisperX and initializes transcription and diarization
models in `transcribe_audio.py`; cached files avoid downloads, but loading models
into RAM/GPU takes time. `main.py` still performs its existing startup database
cleanup and rulebook embedding if embeddings are missing. Eliminating those
costs would require Python behavior changes and is outside this optimization.
GPU CUDA wheels also require a compatible build platform; the existing image is
not guaranteed to build natively on Apple Silicon.

## Verification

After Docker is running and `backend/.env` parses correctly:

```sh
docker compose -f dockerCompose.yml config --quiet
docker compose -f dockerCompose.yml --progress=plain build backend
docker compose -f dockerCompose.yml --progress=plain build backend
```

On the second build, expect all filesystem-changing build steps to say `CACHED`,
including CUDA/ML installs, three model downloads, application pip install, and
source copy. Image export and metadata resolution may still perform work.

With the backend running, edit a Python file and inspect backend logs for the
uvicorn reload. No image build runs, so pip and build-time model downloads cannot
run. An explicit backend build after that edit should invalidate only source
copy. Next make an intended application requirement edit and build `backend`
again: CUDA/ML and model steps should remain `CACHED`, while application pip runs
and can reuse its download cache. The backend-only build output should contain
no frontend npm or Ollama pull steps. Use the backend-only `up` command above to
apply the image; this preserves unrelated running services.

Workspace validation: the ordinary build command was attempted but Compose
rejected the existing local `.env` at line 1. A temporary override omitting that
env file passed Compose configuration validation, but the build could not connect
to Docker: `/Users/rihandsa/.docker/run/docker.sock` was absent. Consequently
second-build `CACHED` output, live reload, dependency rebuilds, runtime startup
and package compatibility could not be verified. No secrets or local `.env`
contents were modified. The behaviors above follow from inspected layer order
and Compose service selection, and still require those live checks.

Static validation confirmed that expanding `requirements.txt` includes exactly
the original requirement specifications, all five pip steps use cache mounts,
and all model downloads precede application requirements/source. Base and map
Compose configuration passed with the temporary env-file override. The installed
Compose v2.29.7 rejects the existing GPU override's `gpus` property; GPU validation
requires a Compose version supporting that property. `git diff --check` passed.
