"""Simple web visualizer for Agent state."""

import logging
try:
    from flask import Flask, render_template_string
except ImportError:
    Flask = None

log = logging.getLogger(__name__)

def start_visualizer(port=8765):
    if not Flask:
        log.error("Flask is not installed. Visualizer cannot start.")
        return
        
    app = Flask(__name__)
    
    # Very simple page to show state
    HTML = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Local Agent Visualizer</title>
        <style>
            body { font-family: sans-serif; background: #121212; color: #fff; text-align: center; margin-top: 50px; }
            h1 { font-size: 3em; }
            .state { font-size: 2em; padding: 20px; background: #333; display: inline-block; border-radius: 10px; }
        </style>
    </head>
    <body>
        <h1>Local Agent</h1>
        <div class="state" id="state-display">IDLE</div>
        <p>This is a placeholder for the visualizer. In a full implementation, this would connect via WebSockets to the agent loop.</p>
    </body>
    </html>
    """

    @app.route('/')
    def index():
        return render_template_string(HTML)
        
    log.info("Starting visualizer on port %d...", port)
    app.run(port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    start_visualizer()
