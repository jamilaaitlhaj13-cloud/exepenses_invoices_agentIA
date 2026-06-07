"""
État partagé du pipeline — module singleton.
Importé (pas exécuté comme script), donc préservé entre les reruns Streamlit.
Le thread et la page UI lisent/écrivent dans ce même objet en mémoire.
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
    "failed":       0,
    "current_file": "",
    "events":       [],   # liste de strings, les plus récents en premier
}


def add_event(icon: str, message: str):
    ts = datetime.now().strftime("%H:%M:%S")
    entry = f"{ts}  {icon}  {message}"
    with _lock:
        STATE["events"].insert(0, entry)
        if len(STATE["events"]) > 60:
            STATE["events"].pop()


def reset(interval_minutes: int = 5, stop_evt: threading.Event = None):
    """Réinitialise l'état avant un nouveau lancement."""
    with _lock:
        STATE["running"]      = True
        STATE["stop_evt"]     = stop_evt or threading.Event()
        STATE["cycles"]       = 0
        STATE["total"]        = 0
        STATE["validated"]    = 0
        STATE["failed"]       = 0
        STATE["current_file"] = ""
        STATE["events"]       = []
