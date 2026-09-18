# ObsidianxOllama

A fully local Windows assistant. It answers questions with Ollama, launches apps,
opens Google searches, and reads and writes your Obsidian vault. Voice input and
spoken replies are optional and run entirely on your machine.

```
ObsidianxOllama/
├── frontend    → React UI
└── backend     → local assistant engine
```

There is no cloud service, no API key, no vector database and no agent framework.
The backend is six flat files. The frontend is a simple React interface.

## Quick start

### Backend

```bat
cd backend

python -m venv assist
assist\Scripts\activate

pip install -r requirements.txt

ollama pull qwen3:1.7b

python -m uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`.

### Frontend

```bat
cd frontend

npm install
npm run dev
```

Open `http://localhost:5173` in your browser.

## Configuration

Edit `backend/config.json`:

- **Ollama**: set `ollama.host` and `ollama.model` if needed
- **Obsidian**: set `obsidian.vault` to your vault folder path
- **Voice**: leave `voice.enabled` true to allow push-to-talk

## What it can do

- Answer questions with Ollama
- Open apps (Chrome, Edge, Notepad, VS Code, etc.)
- Search Google
- Search, read, create, and append to Obsidian notes
- Voice input with silence detection and STT
- Spoken responses via TTS

## Tests

```bat
cd backend
python -m pytest
```

All tests pass without requiring Ollama, a microphone, or a real vault.

## Security

- Applications come from a fixed alias table
- Websites and folders are fixed lists
- Obsidian paths are confined to the vault (path traversal protection)
- No shell commands, no arbitrary execution
- Creating and appending to notes always requires confirmation


```bat
cd local-agent
python main.py
```

Startup prints:

```text
================================
       Local Assistant
================================

Ollama: connected
Model: qwen3:1.7b
Obsidian: configured
Voice: ready

Assistant ready.

Type a command or press Enter for voice.
Type 'quit' to exit.
```

## Commands

Every recognised phrase lives in **one file**: `local-agent/commands.py`. It only
describes *what a sentence means*; nothing in it launches an app, opens a file,
writes a note or calls the model.

```text
typed text  ---+
               |        (voice: Enter -> record -> STT -> text)
               v
      commands.recognize()      <- commands.py (pure, deterministic)
               v
            core.py             <- decides what to do, asks before writing
               v
   tools.py / obsidian.py / ollama.py
               v
            response
```

Typed input and speech both go through `core.Assistant.handle()`, so voice and
text share the same router, the same vocabulary and the same confirmation rules.

* Obvious commands are recognised without the model: apps, websites, folders,
  web search, note search/read/create/append/list, help, status, model info,
  voice mode, repeat, cancel, diagnostics.
* Anything that is not a confident command is sent to Ollama as a normal
  question. There is no attempt to force every sentence into a command.

### Adding a phrase

| What you want | Where to edit |
| --- | --- |
| A new fixed sentence | `COMMANDS["INTENT"]` in `commands.py` |
| A sentence with a variable part | `COMMAND_PATTERNS["INTENT"]` (groups `q`, `name`, `note`, `content`) |
| A new application | `APP_ALIASES` in `tools.py` -- all "open/launch/start/run/bring up ..." phrasings come for free |
| A new website | `WEBSITES` in `tools.py` |
| A new folder | `FOLDERS` in `tools.py` |

Example: to make `fire up notepad` work, add `"fire up"` to `APP_VERBS` in
`commands.py`. To add the Telegram app, add `"telegram": ("telegram.exe", [])`
to `APP_ALIASES` in `tools.py`; the phrase `open telegram` then works in every
verb form.

### Which commands ask first

`create an Obsidian note ...` and `append this to my ... note ...` always ask
`[y/N]` before writing. Everything else -- questions, apps, websites, folders,
web search, note search, note read, note list, help, status -- runs immediately.

### Safety rules built into the vocabulary

* Applications come from a fixed alias table; a name that is not in it is never
  passed to the operating system.
* Websites and folders are fixed lists; user text never becomes a URL or a path.
* Shells and terminals (`open powershell`, `open cmd`, ...) are recognised so the
  assistant can answer, but they are deliberately never launched.
* Obsidian paths are confined to the vault, so `../../test.txt` is rejected.

## Text commands

Questions (anything not recognised below) are answered by Ollama:

```text
> what is ROCE?
```

Apps - the name must be one of the aliases in `tools.py` (chrome, edge, firefox,
notepad, calculator, explorer, paint, vs code, obsidian, spotify, settings, ...):

```text
> open chrome
Opening Chrome.
```

Google search:

```text
> search Google for BBA analytics internships
> search for Python internships
> search the web for Python internships
> look up Python internships
Opening Google search.
```

Obsidian:

```text
> find my notes about portfolio analysis
> search my notes for portfolio analysis
> read my note called Investment Analysis
> create an Obsidian note called Investment Ideas
Create "Investment Ideas.md" in your Obsidian vault? [y/N]
> append this to my Investment Ideas note: buy index funds
Append to "Investment Ideas.md" in your Obsidian vault? [y/N]
```

Creating and appending always ask for confirmation first; everything else runs
immediately. Notes are always `.md`, nested paths such as `Projects/Ideas` work, and
any path that tries to leave the vault (`../../test.txt`, `C:\Windows\...`) is
rejected.

## Voice commands

Press **Enter** on an empty line, then speak:

```text
>
Listening...
You said: what is ROCE?

[answer, spoken aloud]
```

## Configuration

`local-agent/config.json` is the single source of truth; defaults live in `main.py`
so a missing or broken file never stops startup.

## Known limitations

- Replies are spoken only for voice input; typed answers are printed.
- App launching is limited to the alias table in `tools.py`, websites to the
  `WEBSITES` table and folders to the `FOLDERS` table. There is no shell, so
  arbitrary commands cannot be run (by you or by the model). Shell requests such
  as "open powershell" are recognised and politely refused.
- Google search opens your default browser; it does not scrape or read pages.
- Vault search is a simple filename + text match over `.md` files. No index, no
  embeddings, no "semantic memory".
- Windows only (uses `os.startfile` for URI protocols such as `ms-settings:`).
- One utterance per Enter press. There is no wake word and no always-on listening.

## Tests

```bat
cd local-agent
python -m pytest
```

The tests mock Ollama, the browser, the microphone and the speakers, and use
temporary folders for the vault, so nothing external is required.
