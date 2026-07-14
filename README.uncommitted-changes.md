# Setup guide for the current uncommitted changes

This document covers only the pending changes in this workspace. It is intended for setting up the same state on another device without describing the whole project.

## What changed in this patch

- The Prithvi model path now defaults to the workspace-local folder at the repository root:
  - [Prithvi-EO-1.0-100M](Prithvi-EO-1.0-100M)
- Prithvi embedding inference no longer falls back to a random stub embedding. If the model or inference fails, the request now raises an error.
- Sync cancellation now stops the active pipeline work while it is running, including GEE fetching and embedding generation, and the UI progress state reflects cancellation.
- Unit tests were added for the new cancellation and embedding behavior.

## Setup on another device

### 1. Clone or copy the repo

Make sure the repository root contains the Prithvi model folder:

- [Prithvi-EO-1.0-100M](Prithvi-EO-1.0-100M)

If the model folder is not present, copy it into the repository root before starting the app.

### 2. Backend environment

From the backend folder:

```bash
cd backend
python -m venv .venv312
source .venv312/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

### 3. Backend environment variables

Copy the example env file and make sure these values are set:

```bash
cp .env.example .env
```

In [backend/.env](backend/.env) or [backend/.env.example](backend/.env.example), ensure:

```env
PRITHVI_MODEL_PATH=/home/<your-user>/EcoTwin/EcoTwin/Prithri-EO-1.0-100M
PRITHVI_USE_STUB=false
```
DEFAULT_LOCAL_MODEL_DIR = "local_prithvi_model" present in @ _prithvi_model.py

Use the actual absolute path to your local copy of the model folder.

### 4. Start the backend

```bash
cd backend
source .venv312/bin/activate
uvicorn app.main:app --reload
```

### 5. Start the frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

## Verification steps

### Prithvi model path

Confirm the model path exists:

```bash
cd backend
python - <<'PY'
from pathlib import Path
import os
p = Path(os.environ.get('PRITHVI_MODEL_PATH', '/home/<your-user>/EcoTwin/EcoTwin/Prithvi-EO-1.0-100M'))
print(p)
print(p.exists())
print((p / 'config.json').exists())
print((p / 'Prithvi_EO_V1_100M.pt').exists())
PY
```

### Sync cancellation

1. Start a sync from the UI.
2. Click Cancel while the sync is still running.
3. The status should change to cancelled and the current lake/year should clear.

### Embedding behavior

If the model or inference fails, the backend should now raise an error instead of returning a stub embedding.

## Tests

Run the targeted tests:

```bash
cd backend
source .venv312/bin/activate
python -m pytest -q tests/unit/test_sync_service.py tests/unit/test_prithvi_inference.py
```
