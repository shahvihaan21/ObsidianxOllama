import React from 'react';
import Message from './Message';

export default function Chat({ messages }) {
  if (messages.length === 0) {
    return (
      <div className="chat">
        <div className="empty-state">
          <div className="empty-state-icon">💬</div>
          <p className="empty-state-text">
            Start a conversation by typing a message or clicking the microphone.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="chat">
      {messages.map((msg, idx) => (
        <Message
          key={idx}
          role={msg.role}
          content={msg.content}
          type={msg.type}
        />
      ))}
    </div>
  );
}
