# Local Assistant (Ollama + Obsidian)

A small, fully local Windows assistant. It answers questions with Ollama, launches
apps, opens Google searches, and reads and writes your Obsidian vault. Voice input
and spoken replies are optional and run entirely on your machine.

There is no cloud service, no API key, no vector database and no agent framework.
The whole assistant is six flat files under `local-agent/`:

| File | Responsibility |
| --- | --- |
| `main.py` | Loads config, prints status, runs the interaction loop |
| `core.py` | Command router: obvious commands go straight to a tool, everything else goes to Ollama |
| `ollama.py` | Ollama HTTP client built on `urllib` (no SDK, no requests) |
| `tools.py` | Controlled app launching and Google search |
| `obsidian.py` | Vault search, read, create, append (vault is the security boundary) |
| `voice.py` | Push-to-talk recording with silence detection, faster-whisper STT, pyttsx3 TTS |

## Requirements

- Windows 10 or 11
- Python 3.10 or newer
- [Ollama](https://ollama.com) installed and running
- Optional: a working microphone and speakers for voice

The core (questions, app launching, Google search, Obsidian) uses the Python
standard library only. Everything in `requirements.txt` is for voice and tests.

## Installation

```bat
python -m venv assist
assist\Scripts\activate

cd local-agent
pip install -r requirements.txt

ollama pull qwen3:1.7b

python main.py
```

## Ollama setup

Start Ollama (`ollama serve`, or launch the Ollama app) and confirm it answers:

```bat
curl http://127.0.0.1:11434/api/tags
```

If Ollama is not running the assistant still starts; it simply replies
`Ollama is not running. Start Ollama and try again.`

## Model setup

The default model is `qwen3:1.7b` (small enough for a CPU-only laptop):

```bat
ollama pull qwen3:1.7b
```

Change `ollama.model` in `local-agent/config.json` to use another installed model.
If the model is missing, the assistant tells you the exact `ollama pull` command
to run instead of crashing.

## Obsidian setup

Point `obsidian.vault` in `local-agent/config.json` at your vault folder:

```json
"obsidian": {
    "vault": "C:\\Users\\You\\Documents\\MyVault",
    "max_results": 8
}
```

Leave it empty to run without Obsidian; note commands will reply
`Obsidian vault is not configured.` Everything else keeps working.

## Voice setup

Voice is optional and degrades gracefully. Install the requirements, then:

- Leave `voice.enabled` at `true` to allow push-to-talk.
- `voice.silence_seconds` (default `1.0`) is how long you must stop talking before
  recording ends. Recording always waits for speech first, and
  `voice.max_record_seconds` (default `12`) is only a safety cap.
- `voice.silence_threshold` (default `0.012`) is the loudness that counts as speech.
  Raise it if background noise keeps the microphone open.
- `voice.stt_model` (default `tiny`) is the faster-whisper model; it is downloaded
  once on first use and then kept in memory.
- `tts.enabled` toggles spoken replies. `tts.voice` is a SAPI5 voice id (empty means
  the Windows default) and `tts.rate` is words per minute.

If a package, the microphone or the speech engine is missing, the status line shows
`Voice: unavailable (<reason>)` and text mode keeps working.

## Running

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
- App launching is limited to the alias table in `tools.py`. There is no shell, so
  arbitrary commands cannot be run (by you or by the model).
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
