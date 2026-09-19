# ObsidianxOllama — Local AI Assistant

A fully local, terminal-based AI assistant for Windows. Runs entirely on your
machine — no cloud, no API key, no browser, no web server.

```
You > explain what compound interest is
Assistant > Compound interest is interest calculated on both the initial
            principal and the accumulated interest from previous periods ...

You > find my notes about investing
Assistant > Found 2 note(s):
            - Investment Analysis.md
            - Portfolio Strategy.md

You > read my note called Investment Analysis
Assistant > # Investment Analysis
            ...

You > /status
  Ollama    connected  (model: qwen3:1.7b)
  Obsidian  configured  (C:\Users\Vihaan\Documents\Vault)
  Voice     ready

You > /exit
Goodbye.
```

---

## What it does

- **Answers questions** with a local Ollama model
- **Remembers context** during the session ("What is my name?" works after you tell it)
- **Searches, reads, creates, and appends** to Obsidian notes (via the filesystem)
- **Opens apps** — Chrome, VS Code, Notepad, Obsidian, Spotify, and more
- **Opens websites** — Google, YouTube, GitHub, Gmail, Reddit, and more
- **Searches Google** in your default browser
- **Voice input** (optional) — press Enter on a blank line and speak
- **Spoken replies** (optional) — TTS via Windows SAPI5
- **Persistent session history** — every conversation saved to `data/history/`

---

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com) running locally (`ollama serve`)
- A model pulled in Ollama (`ollama pull qwen3:1.7b`)
- Windows (for app launching and voice — core features work on any OS)

---

## Quick start

```bat
git clone https://github.com/shahvihaan21/ObsidianxOllama
cd ObsidianxOllama\ObsidianxOllama

python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt

ollama pull qwen3:1.7b

python main.py
```

---

## Configuration

Edit **`config.json`** in the project root:

```json
{
    "ollama": {
        "host": "http://127.0.0.1:11434",
        "model": "qwen3:1.7b",
        "timeout": 120
    },
    "obsidian": {
        "vault": "C:\\Users\\Vihaan\\Documents\\MyVault",
        "max_results": 8
    },
    "voice": {
        "enabled": true
    },
    "tts": {
        "enabled": true
    }
}
```

Or use environment variables (copy `.env.example` → `.env`):

```
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:1.7b
VAULT_PATH=C:\Users\Vihaan\Documents\MyVault
```

Environment variables override `config.json`.

---

## CLI commands

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/clear` | Clear the current conversation |
| `/reset` | Reset assistant state (same as `/clear`) |
| `/status` | Show Ollama, Obsidian, and voice status |
| `/model` | Show the active model and host |
| `/history` | List saved conversation sessions |
| `/exit` `/quit` `/q` | Exit the assistant |

Any input that is **not** a slash command is sent to the assistant as a
natural-language request.

---

## Natural-language phrases

### Questions (sent to Ollama)
```
You > what is compound interest?
You > explain the difference between ROE and ROCE
You > summarize the note I just read
```

### Apps — alias must be in the table in `local_agent/tools.py`
```
You > open chrome
You > launch vs code
You > start obsidian
```

### Websites
```
You > open youtube
You > go to github
You > visit google drive
```

### Google search
```
You > search Google for Python internships
You > look up mutual funds
You > search the web for BBA analytics
```

### Obsidian notes
```
You > list my notes
You > find my notes about portfolio analysis
You > search my notes for ROCE
You > read my note called Investment Analysis
You > create a note called Investment Ideas        ← asks for confirmation
You > create a note called Ideas with content Buy index funds
You > append this to my Investment Ideas note: buy index funds   ← asks first
```

### Conversation memory
```
You > My name is Vihaan.
Assistant > Nice to meet you, Vihaan.
You > What is my name?
Assistant > Your name is Vihaan.
```

---

## Obsidian integration

The assistant treats the vault as a normal directory — **Obsidian does not need
to be running**.

- Notes are always `.md` files
- Nested paths work: `Projects/2026/Investment Ideas`
- Path traversal is blocked: `../../evil.txt` is rejected
- Creating and appending **always require confirmation** (`[y/N]`)
- Deletion is not supported (safe by design)

Set `obsidian.vault` in `config.json` or `VAULT_PATH` in `.env`.

---

## Voice (optional)

Voice requires `faster-whisper`, `sounddevice`, and `numpy` (all in
`requirements.txt`). TTS uses Windows SAPI5 via `pyttsx3`.

Press **Enter on a blank line** to record. Speak, then stop — silence
detection ends the recording automatically.

If voice packages are not installed the assistant starts normally in text mode.

---

## Project structure

```
ObsidianxOllama/
├── main.py                  ← entry point: python main.py
├── config.json              ← edit this to set vault path and model
├── .env.example             ← environment variable reference
├── requirements.txt
├── .gitignore
│
├── local_agent/
│   ├── __init__.py
│   ├── config.py            ← loads .env + config.json + env vars
│   ├── cli.py               ← interactive REPL loop
│   ├── assistant.py         ← command router + conversation history
│   ├── llm.py               ← Ollama client (stdlib only, no SDK)
│   ├── commands.py          ← vocabulary recognizer (pure, deterministic)
│   ├── tools.py             ← app launch, Google search, websites, folders
│   ├── obsidian.py          ← vault read/write/search with path protection
│   └── voice.py             ← optional STT (faster-whisper) + TTS (pyttsx3)
│
├── data/
│   └── history/             ← JSONL session files (one per run)
│
└── tests/
    ├── conftest.py
    ├── test_assistant.py
    ├── test_obsidian.py
    └── test_tools.py
```

---

## Running tests

```bat
cd ObsidianxOllama
python -m pytest tests/ -v
```

All 90 tests pass without Ollama, a microphone, or a real vault.

---

## Troubleshooting

**Ollama is not running**
```
[Warning] Ollama is not running. Start Ollama with: ollama serve
Then pull the model:  ollama pull qwen3:1.7b
```

**Model not found**
```
Model 'qwen3:1.7b' is not installed. Run: ollama pull qwen3:1.7b
```

**Obsidian not configured**
```
Obsidian  not configured  (set VAULT_PATH or obsidian.vault in config.json)
```
Set the path in `config.json`:
```json
"obsidian": { "vault": "C:\\Users\\Vihaan\\Documents\\MyVault" }
```

**Voice unavailable**
```
Voice  unavailable  (sounddevice is not installed)
```
Install with `pip install faster-whisper sounddevice numpy pyttsx3` or set
`"voice": { "enabled": false }` in `config.json` to silence the warning.

---

## Security

- App launching uses a fixed alias table — arbitrary executables cannot be run
- Shells (`cmd`, `powershell`, `terminal`) are recognised but deliberately blocked
- Website and folder opening uses fixed lists — user text never becomes a URL or path
- Obsidian paths are confined to the configured vault (`../../escape` is rejected)
- Creating and appending to notes always require explicit confirmation
- No shell strings, no `os.system`, no `shell=True` anywhere

---

## License

MIT
