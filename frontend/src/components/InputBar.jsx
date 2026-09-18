import React, { useState, useRef, useEffect } from 'react';
import { sendMessage, sendVoice } from '../services/api';

export default function InputBar({
  onSend,
  disabled,
  listening,
  processing,
  speaking,
  onTranscript,
}) {
  const [input, setInput] = useState('');
  const inputRef = useRef(null);
  const transcriptTimeout = useRef(null);

  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.focus();
    }
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (disabled || !input.trim()) return;

    const message = input.trim();
    setInput('');
    onSend(message);
  };

  const handleVoice = async () => {
    if (listening || processing || disabled) return;

    try {
      const result = await sendVoice();
      if (result.success && result.transcript) {
        onTranscript(result.transcript);
        onSend(result.transcript);
      } else if (result.error) {
        onTranscript(result.error);
        setTimeout(() => onTranscript(null), 3000);
      }
    } catch (err) {
      onTranscript(err.message);
      setTimeout(() => onTranscript(null), 3000);
    }
  };

  const showTranscript = onTranscript && onTranscript._value;
  const micState = listening ? 'listening' : processing ? 'processing' : speaking ? 'speaking' : '';

  const micIcon = listening ? '🎤' : processing ? '◌' : speaking ? '🔊' : '🎙';

  return (
    <div className="input-bar">
      <form onSubmit={handleSubmit} className="input-wrapper">
        <input
          ref={inputRef}
          type="text"
          className="input"
          placeholder="Type a command..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={disabled || listening}
        />
        {showTranscript && (
          <div className={`transcript ${listening ? 'visible' : ''}`}>
            <span className="transcript-label">You said:</span>
            "{showTranscript}"
          </div>
        )}
      </form>

      <button
        type="button"
        className={`mic-btn ${micState}`}
        onClick={handleVoice}
        disabled={disabled || listening || processing}
        title={listening ? 'Listening...' : processing ? 'Processing...' : 'Voice input'}
      >
        {micIcon}
      </button>

      <button
        type="submit"
        className="send-btn"
        onClick={handleSubmit}
        disabled={disabled || !input.trim() || listening}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <line x1="22" y1="2" x2="11" y2="13"></line>
          <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
        </svg>
      </button>
    </div>
  );
}
