# Local Agent

A fully local Windows personal computer agent built on top of Ollama (qwen3:1.7b). It features a robust permission system, local voice STT/TTS (faster-whisper and pyttsx3), and Obsidian memory integration.

## Installation
Run `scripts\install.bat` to install dependencies.

## Usage
Run `scripts\start.bat` or `python main.py`.

## Configuration
Edit `config/config.json` to change the model, voice settings, and Obsidian vault path.

## Architecture
- `agent/`: Core LLM integration and execution loop
- `tools/`: Windows automation and permission boundary
- `voice/`: Local speech-to-text and text-to-speech
- `memory/`: Obsidian vault markdown parsing
- `visualizer/`: Local state display
- `tests/`: Smoke tests, integration tests, and security tests

## Security
The agent operates with three permission levels:
- SAFE: Auto-executes (read files, search)
- MODERATE: Prompts user (write files, notes)
- DANGEROUS: Always prompts (delete files, powershell)
