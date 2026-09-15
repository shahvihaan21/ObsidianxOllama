"""Local Text-to-Speech using pyttsx3 (SAPI5 on Windows)."""

import logging
try:
    import pyttsx3
except ImportError:
    pyttsx3 = None

log = logging.getLogger(__name__)

class TTSEngine:
    def __init__(self, voice_id="", rate=150, volume=1.0):
        self.voice_id = voice_id
        self.rate = rate
        self.volume = volume
        self.engine = None
        self.is_speaking = False

    def _init_engine(self):
        if not pyttsx3:
            return False
        try:
            self.engine = pyttsx3.init()
            self.engine.setProperty('rate', self.rate)
            self.engine.setProperty('volume', self.volume)
            if self.voice_id:
                self.engine.setProperty('voice', self.voice_id)
            return True
        except Exception as e:
            log.error("TTS init error: %s", e)
            return False

    def speak(self, text: str):
        if not text.strip():
            return
        if not self.engine:
            if not self._init_engine():
                return
        
        try:
            self.is_speaking = True
            self.engine.say(text)
            self.engine.runAndWait()
        except Exception as e:
            log.error("TTS speaking error: %s", e)
        finally:
            self.is_speaking = False
    
    def stop(self):
        if self.engine and self.is_speaking:
            try:
                self.engine.stop()
            except Exception:
                pass
            self.is_speaking = False
