import React from 'react';

export default function Message({ role, content, type = 'text' }) {
  const isUser = role === 'user';
  const contentClass = type === 'tool' ? 'tool' : type === 'error' ? 'error' : '';

  return (
    <div className={`message ${isUser ? 'user' : 'assistant'}`}>
      {!isUser && <div className="message-label">Assistant</div>}
      <div className={`message-content ${contentClass}`}>
        {content}
      </div>
      {isUser && <div className="message-label">You</div>}
    </div>
  );
}
