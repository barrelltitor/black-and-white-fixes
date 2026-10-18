"""Synthetic fixtures only: no game files are bundled or required."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch
import patch_creature_isle as ci_patcher
import patch_black_and_white as base_patcher


def fixture_spec():
    original, changed = b"ABCDEFGHIJ", b"ABxyEFGHIJ"
    return original, changed, {
        "original": ci_patcher.digest(original), "patched": ci_patcher.digest(changed),
        "edits": [(2, b"CD", b"xy")],
    }


class PatcherTests(unittest.TestCase):
    patcher = ci_patcher

    def test_alternate_build_selects_its_own_checksums(self):
        original, changed, spec = fixture_spec()
        with patch.dict(self.patcher.ALTERNATE_BUILDS, {self.patcher.TARGET_EXE: [spec]}):
            self.assertIs(self.patcher.select_spec(original, self.patcher.TARGET_EXE), spec)
            self.assertIs(self.patcher.select_spec(changed, self.patcher.TARGET_EXE), spec)
            self.assertEqual(self.patcher.transform(original, spec, "patched"), changed)
            self.assertEqual(self.patcher.transform(changed, spec, "original"), original)

    def test_reversible_and_idempotent(self):
        original, changed, spec = fixture_spec()
        self.assertEqual(self.patcher.transform(original, spec, "patched"), changed)
        self.assertEqual(self.patcher.transform(changed, spec, "original"), original)
        self.assertEqual(self.patcher.transform(changed, spec, "patched"), changed)

    def test_unknown_input_rejected(self):
        _, _, spec = fixture_spec()
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            self.patcher.transform(b"unrelated", spec, "patched")

    def test_wrong_patch_definition_rejected(self):
        original, _, spec = fixture_spec()
        spec["edits"] = [(2, b"NO", b"xy")]
        with self.assertRaisesRegex(ValueError, "signature"):
            self.patcher.transform(original, spec, "patched")

    def test_unexpected_output_rejected(self):
        original, _, spec = fixture_spec()
        spec["patched"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "Output checksum"):
            self.patcher.transform(original, spec, "patched")

    def test_apply_backup_restore_and_noop(self):
        original, changed, spec = fixture_spec()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(self.patcher.PATCHES, {self.patcher.TARGET_EXE: spec}):
            folder = Path(tmp)
            target = folder / self.patcher.TARGET_EXE
            target.write_bytes(original)
            with redirect_stdout(io.StringIO()):
                backup = self.patcher.run("apply", folder)
                self.assertEqual((backup / target.name).read_bytes(), original)
                self.assertEqual(target.read_bytes(), changed)
                self.assertIsNone(self.patcher.run("apply", folder))
                self.patcher.run("restore", folder)
                self.assertEqual(target.read_bytes(), original)

    def test_unsupported_executable_rejected_before_backup(self):
        original, _, spec = fixture_spec()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(self.patcher.PATCHES, {self.patcher.TARGET_EXE: spec}):
            folder = Path(tmp)
            target = folder / self.patcher.TARGET_EXE
            target.write_bytes(b"unsupported")
            with redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
                self.patcher.run("apply", folder)
            self.assertEqual(target.read_bytes(), b"unsupported")
            self.assertFalse((folder / ".ci-screenshot-fix-backups").exists())

    def test_only_executable_is_changed(self):
        original, _, spec = fixture_spec()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(self.patcher.PATCHES, {self.patcher.TARGET_EXE: spec}):
            folder = Path(tmp)
            (folder / self.patcher.TARGET_EXE).write_bytes(original)
            untouched = folder / "other.dll"
            untouched.write_bytes(b"leave this alone")
            with redirect_stdout(io.StringIO()):
                self.patcher.run("apply", folder)
            self.assertEqual(untouched.read_bytes(), b"leave this alone")

    def test_cli_requires_executable_beside_script(self):
        with tempfile.TemporaryDirectory() as script_tmp, tempfile.TemporaryDirectory() as cwd_tmp:
            script = Path(script_tmp) / "patch_creature_isle.py"
            script.write_bytes(Path(self.patcher.__file__).read_bytes())
            target = Path(cwd_tmp) / self.patcher.TARGET_EXE
            target.write_bytes(b"must not inspect the working directory")
            result = subprocess.run([sys.executable, str(script)], cwd=cwd_tmp, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(Path(script_tmp).name, result.stderr)
            self.assertNotIn(Path(cwd_tmp).name, result.stderr)
            self.assertEqual(target.read_bytes(), b"must not inspect the working directory")

    def test_backup_failure_prevents_changes(self):
        original, _, spec = fixture_spec()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(self.patcher.PATCHES, {self.patcher.TARGET_EXE: spec}):
            folder = Path(tmp)
            target = folder / self.patcher.TARGET_EXE
            target.write_bytes(original)
            with patch.object(self.patcher, "backup_files", side_effect=OSError("backup unavailable")):
                with redirect_stdout(io.StringIO()), self.assertRaises(OSError):
                    self.patcher.run("apply", folder)
            self.assertEqual(target.read_bytes(), original)

    def test_replacement_failure_preserves_original_and_backup(self):
        original, _, spec = fixture_spec()
        with tempfile.TemporaryDirectory() as tmp, patch.dict(self.patcher.PATCHES, {self.patcher.TARGET_EXE: spec}):
            folder = Path(tmp)
            target = folder / self.patcher.TARGET_EXE
            target.write_bytes(original)
            with patch.object(self.patcher.os, "replace", side_effect=PermissionError("game running")):
                with redirect_stdout(io.StringIO()), self.assertRaises(PermissionError):
                    self.patcher.run("apply", folder)
            self.assertEqual(target.read_bytes(), original)
            backups = list((folder / ".ci-screenshot-fix-backups").glob("*/" + self.patcher.TARGET_EXE))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), original)
            self.assertFalse(list(folder.glob(".ci-fix-*")))


class BaseGamePatcherTests(PatcherTests):
    patcher = base_patcher


if __name__ == "__main__":
    unittest.main()
