from datetime import date, timedelta
import fnmatch
import importlib.util
from pathlib import Path
import re
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location(
    "heartbeat", Path(__file__).resolve().parents[1] / "scripts/heartbeat_bilibili_updater.py"
)
heartbeat = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(heartbeat)


class HeartbeatTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.today = date(2026, 11, 9)
        self.target = self.root / heartbeat.HEARTBEAT

    def save(self, text):
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_text(text, encoding="utf-8")

    def test_44_days_does_not_write_or_touch_file(self):
        old = self.today - timedelta(days=44)
        self.save(old.isoformat() + "\n")
        before = self.target.stat().st_mtime_ns
        self.assertFalse(heartbeat.update_heartbeat(self.root, self.today, old))
        self.assertEqual(before, self.target.stat().st_mtime_ns)

    def test_45_days_writes_utc_iso_date_once(self):
        old = self.today - timedelta(days=45)
        self.save(old.isoformat() + "\n")
        self.assertTrue(heartbeat.update_heartbeat(self.root, self.today, old))
        self.assertEqual("2026-11-09\n", self.target.read_text())
        self.assertFalse(heartbeat.update_heartbeat(self.root, self.today, old))

    def test_recent_rule_commit_postpones_old_heartbeat(self):
        self.save((self.today - timedelta(days=50)).isoformat())
        self.assertFalse(heartbeat.update_heartbeat(self.root, self.today, self.today - timedelta(days=1)))

    def test_future_heartbeat_cannot_disable_idle_keepalive(self):
        self.save("2099-01-01\n")
        self.assertTrue(heartbeat.update_heartbeat(self.root, self.today, self.today - timedelta(days=45)))
        self.assertEqual("2026-11-09\n", self.target.read_text())

    def test_future_heartbeat_with_recent_commit_does_not_create_noise(self):
        self.save("2099-01-01\n")
        self.assertFalse(heartbeat.update_heartbeat(self.root, self.today, self.today))

    def test_first_empty_file_uses_repository_activity(self):
        self.save("")
        self.assertFalse(heartbeat.update_heartbeat(self.root, self.today, self.today))
        self.assertTrue(heartbeat.update_heartbeat(self.root, self.today, self.today - timedelta(days=45)))

    def test_first_missing_file_does_not_add_a_commit_to_an_active_repo(self):
        self.assertFalse(heartbeat.update_heartbeat(self.root, self.today, self.today))
        self.assertFalse(self.target.exists())

    def test_first_missing_file_initializes_an_idle_repo(self):
        self.assertTrue(heartbeat.update_heartbeat(self.root, self.today, self.today - timedelta(days=45)))
        self.assertEqual("2026-11-09\n", self.target.read_text())

    def test_malformed_and_future_commit_dates_do_not_lock_out_updates(self):
        self.save("not-a-date")
        self.assertTrue(heartbeat.update_heartbeat(self.root, self.today, date(2099, 1, 1)))

    def test_heartbeat_does_not_match_workflow_push_triggers(self):
        workflow = (SPEC.origin and Path(SPEC.origin).parents[1] / ".github/workflows/update-bilibili-pcdn.yml").read_text()
        push = workflow.split("  push:\n", 1)[1].split("  pull_request:", 1)[0]
        patterns = re.findall(r"- '([^']+)'", push)
        self.assertTrue(patterns)
        self.assertTrue(any(fnmatch.fnmatchcase("scripts/heartbeat_bilibili_updater.py", p) for p in patterns))
        self.assertFalse(any(fnmatch.fnmatchcase(heartbeat.HEARTBEAT.as_posix(), p) for p in patterns))


if __name__ == "__main__":
    unittest.main()
