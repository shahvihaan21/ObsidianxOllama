# Local Assistant Frontend

A lightweight React + Vite interface for the local assistant backend.

## Architecture

```
frontend/
├── src/
│   ├── components/     # React components
│   │   ├── Header.jsx      # Assistant name, status, model
│   │   ├── Chat.jsx        # Message display area
│   │   ├── Message.jsx     # Individual message rendering
│   │   ├── InputBar.jsx    # Text input + microphone button
│   │   └── StatusIndicator.jsx
│   ├── services/
│   │   └── api.js          # All API calls to the backend
│   ├── styles/
│   │   └── app.css         # Dark theme styles
│   ├── App.jsx             # Main application component
│   └── main.jsx           # Entry point
├── public/
├── package.json
├── vite.config.js
└── README.md
```

The frontend is only the interface. It does NOT contain any of the assistant
logic -- no Ollama, no STT, no TTS, no tool execution, no Obsidian access.

## Setup

```bash
cd frontend

npm install
npm run dev
```

The frontend starts at `http://localhost:5173` and connects to the backend at
`http://127.0.0.1:8000` by default.

## Configuration

To use a different backend URL, set the environment variable:

```bash
# In your shell before running:
set VITE_API_URL=http://127.0.0.1:8000
npm run dev
```

Or create a `.env` file in the frontend directory:

```
VITE_API_URL=http://127.0.0.1:8000
```

## Development

- `npm run dev` - Start the development server with hot reload
- `npm run build` - Build for production
- `npm run preview` - Preview the production build

## State Management

The frontend uses React state only. No Redux, Zustand, or other state libraries.

State maintained:

- `messages` - conversation history
- `input` - text input value
- `loading` - whether a request is in progress
- `listening` - whether the microphone is active
- `processing` - whether voice is being processed
- `speaking` - whether TTS is playing
- `backendStatus` - connection status from health checks
- `model` - the Ollama model name

## API Service

All API calls go through `src/services/api.js`:

- `checkHealth()` - GET /api/health
- `sendMessage(message)` - POST /api/chat
- `sendVoice()` - POST /api/voice

Do not scatter `fetch(...)` calls throughout components.

## Design

Dark theme, clean typography, restrained accent color, rounded panels, subtle
borders, minimal shadows, smooth transitions, generous spacing.

The assistant is the focus. No gauges, charts, fake statistics, or decorative
dashboards.

## Features

- Text chat with the local assistant
- Voice input via microphone button
- Real-time backend status indicator
- Model name display
- Loading state during requests
- Error handling with user-friendly messages
- Transcript display during voice interactions
- Responsive layout for desktop and laptop screens
