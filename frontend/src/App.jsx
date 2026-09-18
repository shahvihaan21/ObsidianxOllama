import React, { useState, useEffect, useCallback, useRef } from 'react';
import Header from './components/Header';
import Chat from './components/Chat';
import InputBar from './components/InputBar';
import { checkHealth, sendMessage } from './services/api';

const initialMessages = [];
const loadingMessages = { role: 'assistant', content: '', type: 'loading' };

export default function App() {
  const [messages, setMessages] = useState(initialMessages);
  const [loading, setLoading] = useState(false);
  const [listening, setListening] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [backendStatus, setBackendStatus] = useState('unknown');
  const [model, setModel] = useState('');
  const [transcript, setTranscript] = useState(null);
  const chatEndRef = useRef(null);

  // Scroll to bottom when messages change
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Health check on mount
  useEffect(() => {
    const check = async () => {
      try {
        const health = await checkHealth();
        setBackendStatus(health.status);
        setModel(health.model);
      } catch {
        setBackendStatus('offline');
      }
    };
    check();

    // Periodic health check every 30 seconds
    const interval = setInterval(check, 30000);
    return () => clearInterval(interval);
  }, []);

  const addMessage = useCallback((role, content, type = 'text') => {
    setMessages(prev => [...prev, { role, content, type }]);
  }, []);

  const handleSend = async (message) => {
    // Add user message immediately
    addMessage('user', message);

    // Show loading state
    setLoading(true);
    addMessage('assistant', '', 'loading');

    try {
      const result = await sendMessage(message);
      // Remove loading message
      setMessages(prev => prev.slice(0, -1));

      if (result.success && result.response) {
        addMessage('assistant', result.response);
      } else {
        addMessage('assistant', result.response || 'No response.', 'error');
      }
    } catch (err) {
      // Remove loading message
      setMessages(prev => prev.slice(0, -1));
      addMessage('assistant', err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleTranscript = (text) => {
    setTranscript(text);
    if (text === null) {
      setTimeout(() => setTranscript(null), 500);
    }
  };

  return (
    <div className="app">
      <Header status={backendStatus} model={model} />
      <Chat messages={messages} />
      <InputBar
        onSend={handleSend}
        disabled={loading}
        listening={listening}
        processing={processing}
        speaking={speaking}
        onTranscript={handleTranscript}
      />
      <div ref={chatEndRef} />
    </div>
  );
}
