const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

async function request(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (!response.ok) {
    let errorMessage = 'Unable to reach the assistant backend.';
    try {
      const errorData = await response.json();
      errorMessage = errorData.detail || errorData.error || errorMessage;
    } catch {
      // Use default message if response is not JSON
    }
    throw new Error(errorMessage);
  }

  return response.json();
}

export function checkHealth() {
  return request('/api/health');
}

export function sendMessage(message) {
  return request('/api/chat', {
    method: 'POST',
    body: JSON.stringify({ message }),
  });
}

export function sendVoice() {
  return request('/api/voice', {
    method: 'POST',
  });
}

export function getStatus() {
  return request('/api/status');
}
