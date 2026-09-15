# Migration Map — Claude → Local Ollama

This document records Phase 0 of the build: what was inspected, what was kept
conceptually, and what was replaced. **No code was copied from the reference
repositories.** This project is a clean-room reimplementation of the
_architecture_ using local components only.

## Reference repositories inspected

| Repo              | Language                | What it actually is                                     | License           |
| ----------------- | ----------------------- | ------------------------------------------------------- | ----------------- |
| `fullstack-agent` | Batch/Shell             | Installer/wizard that assembles the four pieces below   | AGPL-3.0-or-later |
| `backtalk`        | Python 93%              | Push-to-talk voice line; STT + TTS run **locally**      | AGPL-3.0-or-later |
| `ai-memory-vault` | Markdown + build script | Obsidian vault as persistent memory + "Jobs"            | CC BY-SA 4.0      |
| `ai-visualizer`   | HTML/JS + stdlib Python | Full-screen faces driven by a **file-based signal bus** | AGPL-3.0-or-later |
| `barehands`       | HTML/JS + stdlib Python | Webcam hand tracking (MediaPipe), optional              | AGPL-3.0-or-later |

## The single Claude coupling point

Everything Claude-specific lives in **one place in the original stack**: the
"brain". `backtalk` is explicitly described as "a mouth and ears for whoever you
already have" — its ears (`faster-whisper`) and mouth (`Kokoro`) are already
local and free. `fullstack-agent` is a _Claude Code wizard_. `ai-memory-vault`
instructs a Claude agent to read/write files. `ai-visualizer` and `barehands`
never touch an LLM at all and drive off files.

**Therefore the migration is narrow:** replace the brain, keep the pipes.

## Concept-by-concept replacement

| Original component                               | Replacement in this project                                | Reason                                                                                                                                                                                                   |
| ------------------------------------------------ | ---------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Claude Agent SDK session (`backtalk` brain)      | `agent/ollama_client.py` + `agent/agent_loop.py`           | Native Ollama `/api/chat` with native `tools=` calling. `qwen3:1.7b` reports capability `tools`, verified live.                                                                                          |
| `CLAUDE.md` boot config                          | `AGENT.md` + `agent/prompts.py`                            | Plain file read at startup; no vendor coupling.                                                                                                                                                          |
| Claude Code auto-loaded project context          | `prompts/system.md` + JIT vault retrieval                  | Context is _pulled_ on demand instead of preloaded — required on 8 GB RAM.                                                                                                                               |
| Claude Code tool invocation (MCP)                | `tools/registry.py` + `tools/*.py`                         | A ~200-line registry with JSON schemas. No MCP transport needed in-process.                                                                                                                              |
| Claude Code permission prompts                   | `agent/permissions.py` (3 levels)                          | Enforced **in Python**, never delegated to the model.                                                                                                                                                    |
| Claude Code session / `resume_last_session`      | `agent/session.py`                                         | JSON session log on disk, resumable.                                                                                                                                                                     |
| Claude Code native memory (`~/.claude/projects`) | `memory/` package → Obsidian vault                         | One memory layer, not two. Avoids the "two layers that drift apart" problem the original warns about.                                                                                                    |
| `ai-memory-vault` `CLAUDE.md` boot config        | `VAULT-INDEX.md` + `PROFILE.md` templates                  | Same files, now read by our own agent.                                                                                                                                                                   |
| `ai-memory-vault` "Jobs"                         | `memory/vault.py` job discovery                            | Same markdown format: objective / steps / output / constraints.                                                                                                                                          |
| `ai-memory-vault` AI Priming                     | `search_memory` → read → inject                            | Just-in-time retrieval, token-budgeted.                                                                                                                                                                  |
| backtalk STT (`faster-whisper`)                  | `voice/stt.py` (faster-whisper)                            | Already local + MIT. Kept, with an energy-based VAD so we don't add `webrtcvad`.                                                                                                                         |
| backtalk TTS (Kokoro + espeak-ng)                | `voice/tts.py` (SAPI5 primary)                             | Kokoro is excellent but pulls ~1 GB of models; on 8 GB with 1.4 GB free, Windows SAPI5 gives zero-install speech. Kokoro is a config switch.                                                             |
| backtalk global talk key                         | `voice/push_to_talk.py`                                    | Same design: mic closed except while the key is held, so the mic never hears the speakers.                                                                                                               |
| backtalk interrupt-on-key                        | `voice/audio_manager.py`                                   | Cooperative cancel token; TTS checks it mid-sentence.                                                                                                                                                    |
| `ai-visualizer` browser faces                    | `visualizer/bus.py` (file bus) + optional tiny HTTP server | A browser GUI + JS engine for four faces is pure RAM cost on integrated graphics. The **bus format is preserved** (`.voice_state`, `.voice_waveform`) so the real visualizer can be pointed at it later. |
| `barehands` hand tracking                        | _not implemented_ (documented as future)                   | MediaPipe + three.js from CDN + webcam. Explicitly excluded from v1 to protect the RAM budget.                                                                                                           |
| Anthropic API key                                | _nothing_                                                  | No cloud LLM, no API key, no billing.                                                                                                                                                                    |

## Architectural ideas deliberately preserved

1. **Adopt, never rebuild.** If a vault exists, use it as-is. Never move it.
2. **Identity lives outside the model.** Name/personality in config + `AGENT.md`.
3. **Ask before acting, in plain words.** Confirmation states what/where/why.
4. **Push-to-talk by default.** Mic physically closed when not held.
5. **File-based state bus.** Any external tool can observe state by reading a file.
6. **No vector database.** Markdown + filename/text search, as the original does.
7. **Just-in-time retrieval.** Never load the whole vault into context.
8. **Memory is intentional.** Do not save every conversation.

## Deliberate deviations

| Deviation                                                          | Reason                                                                                                |
| ------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------- |
| Three explicit permission _levels_ (SAFE/MODERATE/DANGEROUS)       | The original has only ask/auto-approve. A 1.7B model needs _more_ deterministic guarding, not less.   |
| `run_safe_command()` with a whitelist instead of shell passthrough | A small model is more easily steered by injected content from webpages. No general shell tool exists. |
| Tool results truncated by default                                  | A single raw webpage exceeds the model's practical context.                                           |
| Model-agnostic core                                                | `OLLAMA_MODEL` is config; changing it must not touch voice or tools.                                  |

## Attribution

Architecture inspired by Jared Rhodenizer's stack
(`fullstack-agent`, `backtalk`, `ai-memory-vault`, `ai-visualizer`, `barehands`).
Those projects are AGPL-3.0-or-later / CC BY-SA 4.0. This project is an
independent implementation and shares no source code with them; concepts and
file-format conventions are credited here and in `README.md`.
