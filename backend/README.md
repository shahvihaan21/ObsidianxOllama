# Local Assistant Backend

The backend is the actual assistant. It owns Ollama, STT, TTS, command routing,
tool execution, Obsidian, Windows application launching, Google search, and
confirmation.

The frontend is only the interface -- see `../frontend/README.md`.

## Architecture

```
backend/
└── app/
    ├── main.py      # FastAPI app, lifecycle, API endpoints
    ├── core.py      # Command router: user text -> tool or Ollama -> response
    ├── ollama.py    # Ollama HTTP client (urllib, no SDK)
    ├── voice.py     # Recording, STT (faster-whisper), TTS (pyttsx3)
    ├── tools.py     # App launching, Google search, websites, folders
    ├── obsidian.py  # Vault search, read, create, append (path traversal protection)
    └── commands.py  # Command vocabulary: recognition only, no side effects
```

There is no agent loop, no manager, no event bus, no registry. The backend is
six flat files plus the FastAPI glue in `main.py`.

## Configuration

`../backend/config.json` is the single source of truth. Defaults live in
`app/main.py` so a missing or broken file never stops startup.

Key sections:

```json
{
  "ollama": {
    "host": "http://127.0.0.1:11434",
    "model": "qwen3:1.7b",
    "timeout": 120
  },
  "obsidian": {
    "vault": "C:\\Users\\You\\Documents\\MyVault",
    "max_results": 8
  },
  "voice": {
    "enabled": true,
    "language": "en",
    "stt_model": "tiny",
    "silence_seconds": 1.0,
    "max_record_seconds": 12,
    "silence_threshold": 0.012
  },
  "tts": {
    "enabled": true,
    "voice": "",
    "rate": 165
  }
}
```

## Running

```bat
cd backend

python -m venv assist
assist\Scripts\activate

pip install -r requirements.txt

ollama pull qwen3:1.7b

# Start the API server
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

The API is then available at `http://127.0.0.1:8000`.

## API Endpoints

### GET /api/health

Return backend status.

```json
{
  "status": "ok",
  "ollama": true,
  "model": "qwen3:1.7b",
  "voice": true,
  "obsidian": true
}
```

### POST /api/chat

Send a message. The backend internally decides whether the request is normal
chat, an app launch, a Google search, or an Obsidian operation.

Request:

```json
{
  "message": "what is ROCE?"
}
```

Response:

```json
{
  "success": true,
  "response": "ROCE stands for..."
}
```

### POST /api/voice

Trigger a voice interaction. The backend records from the local microphone,
detects silence, transcribes with STT, routes through the core, speaks the
response with TTS, and returns the transcript and response.

```json
{
  "success": true,
  "transcript": "open chrome",
  "response": "Opening Chrome."
}
```

### GET /api/status

Return a detailed status snapshot for the UI.

## Testing

```bat
cd backend
python -m pytest
```

The tests mock Ollama, the browser, the microphone and the speakers, and use
temporary folders for the vault, so nothing external is required.
