#!/usr/bin/env python3
"""Keep the scheduled updater active with at most one heartbeat per 45 idle days."""

from datetime import date, datetime, timezone
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
HEARTBEAT = Path(".github/bilibili-updater-heartbeat.txt")
INTERVAL_DAYS = 45


def stored_day(text: str, today: date) -> date | None:
    try:
        value = date.fromisoformat(text.strip())
    except ValueError:
        return None
    # Future or malformed metadata must not postpone all subsequent heartbeats.
    return value if value <= today else None


def is_due(today: date, commit_day: date | None, heartbeat_text: str) -> bool:
    activity = [day for day in (commit_day, stored_day(heartbeat_text, today))
                if day is not None and day <= today]
    return not activity or (today - max(activity)).days >= INTERVAL_DAYS


def latest_commit_day(root: Path) -> date:
    result = subprocess.run(
        ["git", "log", "-1", "--format=%ct"], cwd=root,
        text=True, capture_output=True, check=True,
    )
    return datetime.fromtimestamp(int(result.stdout.strip()), timezone.utc).date()


def update_heartbeat(root: Path, today: date, commit_day: date | None) -> bool:
    target = root / HEARTBEAT
    saved = target.read_text(encoding="utf-8") if target.exists() else ""
    if not is_due(today, commit_day, saved):
        return False
    value = today.isoformat() + "\n"
    if saved == value:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".txt.tmp")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    temporary.replace(target)
    return True


def main():
    changed = update_heartbeat(ROOT, datetime.now(timezone.utc).date(), latest_commit_day(ROOT))
    print("Heartbeat is due; updated " + str(HEARTBEAT) if changed else "Recent repository activity; no heartbeat needed.")


if __name__ == "__main__":
    main()
