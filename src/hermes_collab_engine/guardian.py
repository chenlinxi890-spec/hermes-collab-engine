"""
Guardian v2 — real-time worker monitoring with continuous Leader attention.

Layers:
  1. Leader attention (every N seconds) — streams recent output to Leader for judgment
  2. Passive markers — worker outputs [GUARDIAN:*] → direct action
  3. Rule detection — no output timeout, error loops → fallback
"""

import os
import re
import time
import signal
import logging
import threading
import subprocess

logger = logging.getLogger(__name__)

POLL_INTERVAL = 2           # seconds between temp file reads
NO_OUTPUT_TIMEOUT = 30      # seconds of silence before leader review
MAX_ERROR_REPEAT = 3        # same error line repeated → leader review
LEADER_ATTENTION_INTERVAL = 15  # seconds between leader attention checks
RING_BUFFER_SIZE = 100      # lines of recent output to keep
LEADER_REVIEW_TIMEOUT = 12  # seconds for leader LLM call


class GuardianEvent:
    """A single event recorded by the guardian."""

    def __init__(self, event_type: str, detail: str, payload: dict | None = None):
        self.event_type = event_type
        self.detail = detail
        self.payload = payload or {}
        self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            "type": self.event_type,
            "detail": self.detail,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }


class GuardianThread(threading.Thread):
    """Monitors a running worker's stdout and calls Leader attention periodically.

    The core loop:
      - Reads new stdout from temp file every POLL_INTERVAL seconds
      - Appends to a ring buffer (last RING_BUFFER_SIZE lines)
      - Every LEADER_ATTENTION_INTERVAL seconds, sends recent output to Leader
      - Leader judges: 'correct' → continue | 'off_track:reason' → interrupt
    """

    def __init__(
        self,
        proc: subprocess.Popen,
        tmp_stdout_path: str,
        tmp_stderr_path: str,
        node_id: str,
        run_id: str,
        task_description: str = "",
        leader_review_fn=None,
        no_output_timeout: int = NO_OUTPUT_TIMEOUT,
        leader_attention_interval: int = LEADER_ATTENTION_INTERVAL,
        log_event_fn=None,
    ):
        super().__init__(daemon=True)
        self.proc = proc
        self.tmp_stdout_path = tmp_stdout_path
        self.tmp_stderr_path = tmp_stderr_path
        self.node_id = node_id
        self.run_id = run_id
        self.task_description = task_description
        self.leader_review_fn = leader_review_fn
        self.no_output_timeout = no_output_timeout
        self.leader_attention_interval = leader_attention_interval
        self.log_event_fn = log_event_fn or (lambda *a, **kw: None)

        self.stop_event = threading.Event()
        self.paused = threading.Event()
        self.paused.clear()
        self.events: list[GuardianEvent] = []

        # Ring buffer for recent output
        self._ring = RingBuffer(RING_BUFFER_SIZE)
        self._last_stdout_size = 0
        self._last_stderr_size = 0
        self._no_output_seconds = 0.0
        self._error_lines: dict[str, int] = {}
        self._last_attention_time = 0.0  # when we last called leader attention
        self._attention_count = 0  # how many attention calls made

    def run(self):
        logger.info("[Guardian v2] Started for %s (PID %d)", self.node_id, self.proc.pid)
        self._last_attention_time = time.time()

        while not self.stop_event.is_set():
            if self.proc.poll() is not None:
                self._record("completed", f"Worker exited with code {self.proc.returncode}")
                break

            if self.paused.is_set():
                time.sleep(0.5)
                continue

            try:
                self._poll()
            except Exception as e:
                logger.warning("[Guardian] Poll error: %s", e)

            time.sleep(POLL_INTERVAL)

        logger.info("[Guardian] Stopped for %s", self.node_id)

    # ── Public API ────────────────────────────────────────

    def pause_worker(self, reason: str = ""):
        try:
            os.kill(self.proc.pid, signal.SIGSTOP)
            self.paused.set()
            self._record("need_input", reason or "Worker paused for user input")
        except ProcessLookupError:
            pass

    def resume_worker(self, feedback: str = ""):
        try:
            os.kill(self.proc.pid, signal.SIGCONT)
            self.paused.clear()
            self._record("normal", f"Resumed: {feedback[:100]}" if feedback else "Resumed")
        except ProcessLookupError:
            pass

    def interrupt_worker(self, reason: str = ""):
        try:
            pgid = os.getpgid(self.proc.pid)
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            try:
                self.proc.kill()
            except Exception:
                pass
        self._record("interrupted", reason or "Worker interrupted by guardian")
        self.stop()

    def stop(self):
        self.stop_event.set()

    def get_events(self) -> list[dict]:
        return [e.to_dict() for e in self.events]

    def is_paused(self) -> bool:
        return self.paused.is_set()

    def is_interrupted(self) -> bool:
        return any(e.event_type == "interrupted" for e in self.events)

    def attention_count(self) -> int:
        return self._attention_count

    # ── Internal: Poll ─────────────────────────────────────

    def _poll(self):
        stdout_new = self._read_new(self.tmp_stdout_path, "_last_stdout_size")
        stderr_new = self._read_new(self.tmp_stderr_path, "_last_stderr_size")

        # Append to ring buffer
        if stdout_new:
            self._ring.append(stdout_new)
            self._no_output_seconds = 0.0
        else:
            self._no_output_seconds += POLL_INTERVAL

        # Layer 1: Markers
        if stdout_new:
            self._check_markers(stdout_new)
            self._check_error_loop(stdout_new)

        # Layer 2: Stalled
        if self._no_output_seconds >= self.no_output_timeout:
            self._no_output_seconds = 0.0
            self._do_leader_attention(reason="stalled")

        # Layer 2: Error in stderr
        if stderr_new:
            self._check_error_loop(stderr_new)

        # Layer 1: LEADER ATTENTION (periodic, regardless of markers)
        elapsed = time.time() - self._last_attention_time
        if elapsed >= self.leader_attention_interval and self.leader_review_fn:
            self._do_leader_attention(reason="periodic")

    def _do_leader_attention(self, reason: str = "periodic"):
        """Call Leader to review recent worker output."""
        if not self.leader_review_fn:
            return
        recent = self._ring.recent(30)
        summary = self._ring.summary(5)  # last 5 lines for quick view

        context = (
            f"Task: {self.task_description[:200]}\n"
            f"Worker: {self.node_id}\n"
            f"Runtime: worker has been running\n"
            f"Trigger: {reason}\n"
            f"Recent output (last 30 lines):\n{recent}\n\n"
            f"Is the worker on track? Reply single word:\n"
            f"  correct — worker is making progress in the right direction\n"
            f"  off_track:<reason> — worker is going the wrong way, needs interruption"
        )

        try:
            decision = self.leader_review_fn(context)
            decision = (decision or "").strip().lower()
            self._attention_count += 1
            self._last_attention_time = time.time()

            self._record("leader_attention",
                         f"attention #{self._attention_count}: {decision[:100]}",
                         {"decision": decision, "trigger": reason})

            if decision.startswith("off_track"):
                reason_text = decision.split(":", 1)[1].strip() if ":" in decision else "off track"
                self.interrupt_worker(reason=reason_text)
            # "correct" → do nothing, continue monitoring

        except Exception as e:
            logger.warning("[Guardian] Leader attention failed: %s", e)
            self._last_attention_time = time.time()  # reset timer to avoid spam

    # ── Internal: Helpers ─────────────────────────────────

    def _read_new(self, path: str, size_attr: str) -> str:
        try:
            current = os.path.getsize(path)
            last = getattr(self, size_attr, 0)
            if current > last:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(last)
                    new_data = f.read()
                setattr(self, size_attr, current)
                return new_data
            return ""
        except (FileNotFoundError, OSError):
            return ""

    def _check_markers(self, text: str):
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            if "[GUARDIAN:NEED_INPUT]" in line:
                msg = line.split("[GUARDIAN:NEED_INPUT]")[-1].strip()
                self.pause_worker(reason=msg)
                return
            if "[GUARDIAN:DONE]" in line:
                self._record("completed", "Worker marked as done")
                return

    def _check_error_loop(self, text: str):
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            if "error" in line.lower() or "traceback" in line.lower() or "exception" in line.lower():
                self._error_lines[line] = self._error_lines.get(line, 0) + 1
                if self._error_lines[line] >= MAX_ERROR_REPEAT:
                    self._do_leader_attention(reason="error_loop")
                    self._error_lines[line] = 0

    def _record(self, event_type: str, detail: str, payload: dict | None = None):
        self.events.append(GuardianEvent(event_type, detail, payload))
        try:
            self.log_event_fn("guardian", event_type, detail)
        except Exception:
            pass


class RingBuffer:
    """Fixed-size buffer that keeps the last N lines of text."""

    def __init__(self, max_lines: int = 100):
        self.max_lines = max_lines
        self._lines: list[str] = []

    def append(self, text: str):
        for line in text.split("\n"):
            if line.strip():
                self._lines.append(line.strip())
        # Trim to max_lines
        if len(self._lines) > self.max_lines:
            self._lines = self._lines[-self.max_lines:]

    def recent(self, n: int) -> str:
        """Return last n lines as a single string."""
        return "\n".join(self._lines[-n:]) if self._lines else "(no output yet)"

    def summary(self, n: int) -> str:
        """Return last n lines as single string (short)."""
        return self.recent(n)

    @property
    def line_count(self) -> int:
        return len(self._lines)
