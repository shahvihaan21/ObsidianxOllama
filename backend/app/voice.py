"""Local voice: push-to-talk recording with silence detection, STT and TTS.

Recording is silence-based. It waits for speech, keeps recording while you
talk, and stops after ``silence_seconds`` of quiet. ``max_record_seconds`` is
only a safety cap, never the normal stopping mechanism.

Every dependency is optional: if a package is missing, speech input is
unavailable, or a TTS call fails, the assistant keeps running in text mode.
"""

from __future__ import annotations

import logging
import tempfile
import wave
from pathlib import Path

log = logging.getLogger("voice")

SAMPLE_RATE = 16000
CHANNELS = 1
BLOCK_MS = 30
WAIT_FOR_SPEECH_SECONDS = 5.0


def _optional_import(module: str):
    """Import a voice dependency, or return None when it is not installed."""
    try:
        return __import__(module)
    except Exception:  # noqa: BLE001 - missing package or missing native DLL
        log.debug("optional import failed: %s", module, exc_info=True)
        return None


class Voice:
    """Push-to-talk voice input and spoken output."""

    def __init__(self, voice_config: dict | None = None, tts_config: dict | None = None):
        settings = dict(voice_config or {})
        speech = dict(tts_config or {})

        self.enabled = bool(settings.get("enabled", True))
        self.language = settings.get("language") or "en"
        self.stt_model = settings.get("stt_model") or "tiny"
        self.silence_seconds = float(settings.get("silence_seconds", 1.0))
        self.max_record_seconds = float(settings.get("max_record_seconds", 12))
        self.silence_threshold = float(settings.get("silence_threshold", 0.012))
        self.wait_for_speech_seconds = float(
            settings.get("wait_for_speech_seconds", WAIT_FOR_SPEECH_SECONDS)
        )

        self.tts_enabled = bool(speech.get("enabled", True))
        self.tts_voice = speech.get("voice") or ""
        self.tts_rate = int(speech.get("rate", 165))

        self._sounddevice = _optional_import("sounddevice")
        self._numpy = _optional_import("numpy")
        self._whisper_model = None  # loaded once, on the first transcription
        self._engine = None  # pyttsx3 engine, initialised once
        self.reason = self._input_problem()

    # -- availability ----------------------------------------------------

    def _input_problem(self) -> str:
        """Why speech input is unavailable ("" when it is fine)."""
        if not self.enabled:
            return "voice is disabled in config.json"
        if self._sounddevice is None:
            return "sounddevice is not installed"
        if self._numpy is None:
            return "numpy is not installed"
        try:
            devices = self._sounddevice.query_devices()
        except Exception as exc:  # noqa: BLE001 - no audio subsystem at all
            return f"no microphone available ({exc})"
        if not any(device.get("max_input_channels", 0) > 0 for device in devices):
            return "no microphone was found"
        return ""

    @property
    def stt_available(self) -> bool:
        return not self.reason

    @property
    def available(self) -> bool:
        return self.stt_available

    # -- recording -------------------------------------------------------

    def _record_until_silence(self):
        """Return one mono int16 array, or None when nothing was said."""
        block = int(SAMPLE_RATE * BLOCK_MS / 1000)
        max_frames = max(1, int(self.max_record_seconds * 1000 / BLOCK_MS))
        silence_frames = max(1, int(self.silence_seconds * 1000 / BLOCK_MS))
        wait_frames = max(1, int(self.wait_for_speech_seconds * 1000 / BLOCK_MS))

        collected: list = []
        started = False
        waited = 0
        quiet_run = 0

        with self._sounddevice.InputStream(
            samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16", blocksize=block
        ) as stream:
            while len(collected) < max_frames:
                chunk, _overflowed = stream.read(block)
                loud = self._rms(chunk) >= self.silence_threshold

                if not started:
                    if loud:
                        started = True
                    else:
                        waited += 1
                        if waited >= wait_frames:
                            return None  # waited, heard nothing
                        continue

                collected.append(chunk.copy())
                if loud:
                    quiet_run = 0
                else:
                    quiet_run += 1
                    if quiet_run >= silence_frames:
                        break

        if not started or not collected:
            return None
        return self._numpy.concatenate(collected, axis=0)

    def _rms(self, chunk) -> float:
        """Normalised loudness (0..1) of one block of int16 samples."""
        samples = chunk.astype("float32")
        return float(self._numpy.sqrt(self._numpy.mean(self._numpy.square(samples)))) / 32768.0

    def listen(self) -> str:
        """Record one utterance and transcribe it. "" when nothing usable."""
        if not self.available:
            return ""
        try:
            audio = self._record_until_silence()
        except Exception as exc:  # noqa: BLE001 - the mic can vanish mid-session
            log.warning("Recording failed: %s", exc)
            return ""
        if audio is None or len(audio) == 0:
            return ""
        path = self._write_wav(audio)
        if path is None:
            return ""
        try:
            return self.transcribe(path)
        finally:
            try:
                Path(path).unlink()
            except OSError:
                pass

    def _write_wav(self, audio) -> str | None:
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
                name = handle.name
            with wave.open(name, "wb") as wav_file:
                wav_file.setnchannels(CHANNELS)
                wav_file.setsampwidth(2)
                wav_file.setframerate(SAMPLE_RATE)
                wav_file.writeframes(audio.tobytes())
            return name
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not write the recording: %s", exc)
            return None

    # -- speech to text --------------------------------------------------

    def _load_model(self):
        """Load faster-whisper once; keep it in memory for the session."""
        if self._whisper_model is not None:
            return self._whisper_model
        try:
            from faster_whisper import WhisperModel
        except Exception as exc:  # noqa: BLE001 - not installed, or no wheel
            log.warning("Speech recognition is unavailable: %s", exc)
            return None
        try:
            self._whisper_model = WhisperModel(
                self.stt_model, device="cpu", compute_type="int8"
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not load the Whisper model: %s", exc)
            return None
        return self._whisper_model

    def transcribe(self, wav_path: str) -> str:
        """Return the spoken text, or "" when it cannot be understood."""
        model = self._load_model()
        if model is None:
            return ""
        try:
            segments, _info = model.transcribe(
                wav_path, beam_size=1, language=self.language or None
            )
            return " ".join(segment.text for segment in segments).strip()
        except Exception as exc:  # noqa: BLE001
            log.warning("Transcription failed: %s", exc)
            return ""

    # -- text to speech --------------------------------------------------

    def _ensure_engine(self):
        if self._engine is not None:
            return self._engine
        try:
            import pyttsx3
        except Exception as exc:  # noqa: BLE001 - not installed, or no SAPI
            log.warning("Text to speech is unavailable: %s", exc)
            return None
        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", self.tts_rate)
            if self.tts_voice:
                engine.setProperty("voice", self.tts_voice)
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not start text to speech: %s", exc)
            return None
        self._engine = engine
        return engine

    def speak(self, text: str) -> bool:
        """Speak *text*. Returns False on any failure; never raises."""
        spoken = (text or "").strip()
        if not self.tts_enabled or not spoken:
            return False
        engine = self._ensure_engine()
        if engine is None:
            log.info("TTS failed; the response was printed instead.")
            return False
        try:
            engine.say(spoken)
            engine.runAndWait()
            return True
        except Exception as exc:  # noqa: BLE001 - must never kill the assistant
            log.warning("TTS failed (%s); the response was printed instead.", exc)
            self._engine = None
            return False

    def stop(self) -> None:
        """Interrupt any ongoing speech and release the engine."""
        if self._engine is None:
            return
        try:
            self._engine.stop()
        except Exception:  # noqa: BLE001
            pass
        self._engine = None
