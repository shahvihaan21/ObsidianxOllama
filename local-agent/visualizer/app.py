"""Simple web visualizer and file-based signal bus for Agent state."""

import json
import logging
from pathlib import Path

try:
    from flask import Flask, jsonify, render_template_string
except ImportError:
    Flask = None

log = logging.getLogger(__name__)

DEFAULT_BUS_DIR = Path(__file__).resolve().parent


def write_bus_state(state: str, details: dict | None = None, bus_dir: Path | str | None = None) -> None:
    """Write agent state to the file-based signal bus."""
    target_dir = Path(bus_dir) if bus_dir else DEFAULT_BUS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    state_file = target_dir / ".voice_state"
    data = {
        "state": state,
        "details": details or {},
    }
    try:
        state_file.write_text(json.dumps(data), encoding="utf-8")
    except Exception as e:
        log.warning("Could not write bus state: %s", e)


def read_bus_state(bus_dir: Path | str | None = None) -> dict:
    """Read agent state from the file-based signal bus."""
    target_dir = Path(bus_dir) if bus_dir else DEFAULT_BUS_DIR
    state_file = target_dir / ".voice_state"
    if not state_file.exists():
        return {"state": "IDLE", "details": {}}
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        return {"state": "IDLE", "details": {}}


def create_app(bus_dir: Path | str | None = None):
    """Create Flask application for the visualizer."""
    if not Flask:
        return None

    app = Flask(__name__)

    HTML = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Local Agent Visualizer</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f1117; color: #fff; text-align: center; margin-top: 60px; }
        h1 { font-size: 2.5em; margin-bottom: 20px; font-weight: 600; }
        .card { max-width: 500px; margin: 0 auto; background: #1a1d27; border-radius: 12px; padding: 30px; box-shadow: 0 4px 20px rgba(0,0,0,0.5); }
        .state { font-size: 1.8em; font-weight: bold; padding: 15px 30px; display: inline-block; border-radius: 8px; margin: 20px 0; letter-spacing: 1px; }
        .state-IDLE { background: #2d3748; color: #cbd5e0; }
        .state-THINKING { background: #3182ce; color: #ebf8ff; }
        .state-EXECUTING { background: #d69e2e; color: #fffff0; }
        .state-LISTENING { background: #38a169; color: #f0fff4; }
        .state-SPEAKING { background: #805ad5; color: #faf5ff; }
        .details { font-size: 0.95em; color: #a0aec0; word-break: break-all; min-height: 40px; margin-top: 15px; }
    </style>
</head>
<body>
    <div class="card">
        <h1>Local Agent</h1>
        <div class="state state-IDLE" id="state-display">IDLE</div>
        <div class="details" id="details-display">Ready</div>
    </div>
    <script>
        async function updateState() {
            try {
                const res = await fetch('/api/state');
                const data = await res.json();
                const display = document.getElementById('state-display');
                const details = document.getElementById('details-display');
                display.innerText = data.state || 'IDLE';
                display.className = 'state state-' + (data.state || 'IDLE');
                details.innerText = JSON.stringify(data.details || {});
            } catch (err) {}
        }
        setInterval(updateState, 500);
        updateState();
    </script>
</body>
</html>"""

    @app.route('/')
    def index():
        return render_template_string(HTML)

    @app.route('/api/state')
    def get_state():
        return jsonify(read_bus_state(bus_dir))

    return app


def start_visualizer(port: int = 8765, bus_dir: Path | str | None = None) -> None:
    if not Flask:
        log.error("Flask is not installed. Visualizer cannot start.")
        return
    app = create_app(bus_dir)
    log.info("Starting visualizer on http://127.0.0.1:%d...", port)
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    start_visualizer()
