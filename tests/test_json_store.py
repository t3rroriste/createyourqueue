"""json_store.write_json : une écriture ratée ne doit jamais abîmer le fichier existant."""

import json
import tempfile
import unittest
from pathlib import Path

from json_store import write_json


class WriteJsonTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_writes_then_replaces(self):
        target = self.folder / "data" / "settings.json"
        write_json(target, {"a": 1}, indent=2)
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"a": 1})
        write_json(target, {"a": 2})
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"a": 2})

    def test_failed_write_keeps_previous_content(self):
        target = self.folder / "settings.json"
        write_json(target, {"ok": True})
        with self.assertRaises(TypeError):
            write_json(target, {"bad": object()})
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"ok": True})

    def test_no_temporary_file_is_left_behind(self):
        target = self.folder / "settings.json"
        write_json(target, [1, 2, 3])
        with self.assertRaises(TypeError):
            write_json(target, [object()])
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), ["settings.json"])


if __name__ == "__main__":
    unittest.main()
