import threading
import time
from collections import deque
from pathlib import Path


class LogIngestor:
    def __init__(self, path: str, poll_interval: float = 1.0, max_lines: int = 500):
        self.path = Path(path)
        self.poll_interval = poll_interval
        self._lines = deque(maxlen=max_lines)
        self._lock = threading.Lock()
        self._thread = None
        self._stop_event = threading.Event()
        self._position = 0
        self._last_error = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    def status(self) -> dict:
        return {
            "path": str(self.path),
            "running": bool(self._thread and self._thread.is_alive()),
            "buffered_lines": len(self._lines),
            "last_error": self._last_error
        }

    def get_text(self) -> str:
        with self._lock:
            return "\n".join(self._lines)

    def _run(self):
        while not self._stop_event.is_set():
            try:
                self._read_new_lines()
                self._last_error = None
            except Exception as exc:
                self._last_error = str(exc)
            time.sleep(self.poll_interval)

    def _read_new_lines(self):
        if not self.path.exists():
            raise FileNotFoundError(f"Log file not found: {self.path}")

        file_size = self.path.stat().st_size
        if self._position > file_size:
            # File rotated or truncated
            self._position = 0

        with self.path.open("r", encoding="utf-8", errors="ignore") as handle:
            handle.seek(self._position)
            new_lines = handle.read().splitlines()
            self._position = handle.tell()

        if new_lines:
            with self._lock:
                self._lines.extend(new_lines)
