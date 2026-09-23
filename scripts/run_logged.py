"""Run a task with streamed output, a persistent log and regular elapsed-time updates."""

import argparse
import os
import queue
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--log", type=Path, default=Path(".tools/m2-progress.log"))
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        parser.error("A command is required after --")
    args.log.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    with args.log.open("a", encoding="utf-8", buffering=1) as log:

        def emit(message: str) -> None:
            line = f"{datetime.now(UTC).isoformat(timespec='seconds')} [{args.label}] {message}"
            print(line, flush=True)
            log.write(line + "\n")

        emit("Avvio")
        with subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"},
        ) as process:
            messages: queue.Queue[str | None] = queue.Queue()

            def read() -> None:
                assert process.stdout is not None
                for line in process.stdout:
                    messages.put(line.rstrip())
                messages.put(None)

            thread = threading.Thread(target=read, daemon=True)
            thread.start()
            heartbeat = time.monotonic()
            while True:
                try:
                    message = messages.get(timeout=1)
                    if message is None:
                        break
                    emit(message)
                except queue.Empty:
                    pass
                if time.monotonic() - heartbeat >= 10:
                    emit(f"In corso; trascorsi {time.monotonic() - start:.0f} s")
                    heartbeat = time.monotonic()
            code = process.wait()
            thread.join()
            emit(f"Terminato; codice {code}; durata {time.monotonic() - start:.1f} s")
            return code


if __name__ == "__main__":
    raise SystemExit(main())
