"""Make local_agent importable when pytest is run from the project root."""

import sys
from pathlib import Path

# The project root (contains main.py and local_agent/)
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
