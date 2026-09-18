import React from 'react';

export default function Header({ status, model }) {
  const statusClass = status === 'ok' ? 'online' : status === 'degraded' ? 'degraded' : 'offline';
  const statusText = status === 'ok' ? 'Connected' : status === 'degraded' ? 'Degraded' : 'Offline';

  return (
    <header className="header">
      <div className="header-left">
        <div className="logo">S</div>
        <span className="title">Local Assistant</span>
      </div>
      <div className="status-badge">
        <span className={`status-dot ${statusClass}`} />
        <span>{statusText}</span>
      </div>
      {model && <span className="model-name">{model}</span>}
    </header>
  );
}
