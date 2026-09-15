"""Voice Loop.

Coordinates Push-To-Talk, recording, STT, the Agent Loop, and TTS.
"""

import logging
import threading
import time
from typing import Any

from agent.config import Config
from agent.loop import AgentLoop
from voice.stt import STTEngine
from voice.tts import TTSEngine

try:
    import keyboard
except ImportError:
    keyboard = None

log = logging.getLogger(__name__)

class VoiceLoop:
    def __init__(self, config: Config, agent_loop: AgentLoop):
        self.config = config
        self.agent = agent_loop
        self.stt = STTEngine(model_size=config.voice.stt_model, device=config.voice.stt_device)
        self.tts = TTSEngine(voice_id=config.voice.tts_voice, rate=int(150 * config.voice.speed))
        self.is_running = False
        self.is_recording = False
        self._ptt_key = config.voice.ptt_key or "ctrl+alt+space"

    def start(self):
        if not keyboard:
            log.error("Keyboard library not installed. Cannot use Push-To-Talk.")
            return

        log.info("Starting voice loop. PTT Key: %s", self._ptt_key)
        self.stt.load()
        
        self.is_running = True
        keyboard.add_hotkey(self._ptt_key, self._on_ptt_pressed, suppress=True, trigger_on_release=False)
        
        try:
            while self.is_running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        self.is_running = False
        self.tts.stop()

    def _on_ptt_pressed(self):
        """Handle PTT key press."""
        # 1. Interrupt any ongoing TTS
        if self.tts.is_speaking:
            log.info("Interrupting TTS.")
            self.tts.stop()
            return
        
        if self.is_recording:
            return

        self.is_recording = True
        self.agent.on_event("LISTENING", {})
        log.info("Listening...")
        
        # In a real implementation, we would record from microphone here.
        # For now, we simulate recording and STT.
        # audio_file = record_audio_until_key_release(self._ptt_key)
        
        time.sleep(1) # Simulated recording duration
        log.info("Recording finished. Transcribing...")
        
        self.agent.on_event("THINKING", {})
        # text = self.stt.transcribe(audio_file)
        text = "This is a simulated transcription."
        
        self.is_recording = False
        
        if text:
            log.info("User said: %s", text)
            response = self.agent.run(text)
            
            self.agent.on_event("SPEAKING", {})
            log.info("Agent said: %s", response)
            self.tts.speak(response)
            
            self.agent.on_event("IDLE", {})
