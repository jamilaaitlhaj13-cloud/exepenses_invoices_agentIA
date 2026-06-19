"""
Shared pipeline state — singleton module.
Imported (not run as a script), so preserved across Streamlit reruns.
The background thread and the UI page both read/write this same in-memory object.
"""
import threading
from datetime import datetime

_lock = threading.Lock()

STATE = {
    "running":      False,
    "stop_evt":     threading.Event(),
    "cycles":       0,
    "total":        0,
    "validated":    0,
    "rejected":     0,   # rejected by DiT (non-invoices)
    "failed":       0,
    "current_file": "",
    "events":       [],   # list of strings, most recent first
    "auth_message": "",  # Microsoft device flow message
    "last_error":    "",  # last full traceback
}


def add_event(icon: str, message: str):
    ts = datetime.now().strftime("%H:%M:%S")
    entry = f"{ts}  {icon}  {message}"
    with _lock:
        STATE["events"].insert(0, entry)
        if len(STATE["events"]) > 60:
            STATE["events"].pop()


def reset(interval_minutes: int = 5, stop_evt: threading.Event = None):
    """Resets the state before a new pipeline run."""
    with _lock:
        STATE["running"]      = True
        STATE["stop_evt"]     = stop_evt or threading.Event()
        STATE["cycles"]       = 0
        STATE["total"]        = 0
        STATE["validated"]    = 0
        STATE["rejected"]     = 0
        STATE["failed"]       = 0
        STATE["current_file"] = ""
        STATE["events"]       = []