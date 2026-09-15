"""Local Speech-to-Text using faster-whisper."""

import logging
try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

log = logging.getLogger(__name__)

class STTEngine:
    def __init__(self, model_size="tiny", device="cpu", compute_type="int8"):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.model = None

    def load(self):
        if not WhisperModel:
            log.error("faster-whisper not installed.")
            return False
        try:
            self.model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
            return True
        except Exception as e:
            log.error("Failed to load Whisper model: %s", e)
            return False

    def transcribe(self, audio_file: str) -> str:
        if not self.model:
            if not self.load():
                return ""
        
        try:
            segments, info = self.model.transcribe(audio_file, beam_size=5)
            text = " ".join([segment.text for segment in segments])
            return text.strip()
        except Exception as e:
            log.error("Transcription error: %s", e)
            return ""
