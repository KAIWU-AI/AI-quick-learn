from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install.py"
SPEC = importlib.util.spec_from_file_location("skill_installer", INSTALLER)
assert SPEC and SPEC.loader
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def test_installs_complete_skill_to_custom_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "skills"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(INSTALLER),
                    "--agent",
                    "custom",
                    "--target",
                    str(target),
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            installed = target / "open-source-pr-contributor"
            self.assertTrue((installed / "SKILL.md").is_file())
            self.assertTrue((installed / "scripts" / "contribution_radar.py").is_file())
            self.assertTrue((installed / "references" / "repository-pool.json").is_file())
            legacy_env = os.environ.copy()
            legacy_env["PYTHONIOENCODING"] = "cp1252"
            smoke = subprocess.run(
                [sys.executable, str(installed / "scripts" / "contribution_radar.py"), "--help"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=legacy_env,
            )
            self.assertEqual(smoke.returncode, 0, smoke.stderr)
            self.assertIn("开源贡献候选扫描器", smoke.stdout)

    def test_refuses_overwrite_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "skills"
            command = [
                sys.executable,
                str(INSTALLER),
                "--agent",
                "custom",
                "--target",
                str(target),
            ]
            first = subprocess.run(
                command, check=False, capture_output=True, text=True, encoding="utf-8"
            )
            second = subprocess.run(
                command, check=False, capture_output=True, text=True, encoding="utf-8"
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 2)
            self.assertIn("--force", second.stderr)

    def test_force_update_creates_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "skills"
            command = [
                sys.executable,
                str(INSTALLER),
                "--agent",
                "custom",
                "--target",
                str(target),
            ]
            first = subprocess.run(
                command, check=False, capture_output=True, text=True, encoding="utf-8"
            )
            installed = target / "open-source-pr-contributor"
            marker = installed / "local-marker.txt"
            marker.write_text("old", encoding="utf-8")
            updated = subprocess.run(
                [*command, "--force"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(updated.returncode, 0, updated.stderr)
            backups = list(target.glob("open-source-pr-contributor.backup-*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual((backups[0] / "local-marker.txt").read_text(), "old")
            self.assertFalse(marker.exists())

    def test_validation_requires_repository_pool(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            (root / "SKILL.md").write_text(
                "---\nname: open-source-pr-contributor\ndescription: x\n---\nbody\n",
                encoding="utf-8",
            )
            (root / "scripts" / "contribution_radar.py").write_text("", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                installer.validate_skill_tree(root)

    def test_validation_rejects_invalid_setup_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            (root / "references").mkdir()
            (root / "SKILL.md").write_text(
                "---\nname: open-source-pr-contributor\ndescription: x\n---\nbody\n",
                encoding="utf-8",
            )
            (root / "scripts" / "contribution_radar.py").write_text("", encoding="utf-8")
            (root / "references" / "repository-pool.json").write_text(
                '{"repositories":[{"repo":"owner/repo","difficulty":"low",'
                '"setup":{"level":"tiny","required_commands":[],"platforms":["linux"]}}]}',
                encoding="utf-8",
            )
            with self.assertRaises(RuntimeError):
                installer.validate_skill_tree(root)

    def test_failed_force_update_restores_previous_installation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "open-source-pr-contributor"
            destination.mkdir()
            marker = destination / "local-marker.txt"
            marker.write_text("keep", encoding="utf-8")
            with mock.patch.object(installer.shutil, "copytree", side_effect=OSError("copy failed")):
                with self.assertRaises(OSError):
                    installer.install(destination, force=True, dry_run=False)
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_failed_post_copy_validation_restores_previous_installation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "open-source-pr-contributor"
            destination.mkdir()
            marker = destination / "local-marker.txt"
            marker.write_text("keep", encoding="utf-8")
            with mock.patch.object(
                installer, "validate_skill_tree", side_effect=RuntimeError("invalid copy")
            ):
                with self.assertRaises(RuntimeError):
                    installer.install(destination, force=True, dry_run=False)
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_agents_use_documented_user_skill_directories(self) -> None:
        expected_roots = {
            "hermes": ".hermes/skills",
            "claude": ".claude/skills",
            "codex": ".agents/skills",
        }
        with tempfile.TemporaryDirectory() as directory:
            env = os.environ.copy()
            env["HOME"] = directory
            env["USERPROFILE"] = directory
            for agent, relative_root in expected_roots.items():
                with self.subTest(agent=agent):
                    completed = subprocess.run(
                        [sys.executable, str(INSTALLER), "--agent", agent, "--dry-run"],
                        check=False,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        env=env,
                    )
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    expected = Path(directory) / relative_root / "open-source-pr-contributor"
                    self.assertIn(str(expected), completed.stdout)

    def test_cli_uses_utf8_when_parent_stdio_is_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "cp1252"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(INSTALLER),
                    "--agent",
                    "custom",
                    "--target",
                    str(Path(directory) / "skills"),
                    "--dry-run",
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=env,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("将安装", completed.stdout)

    def test_refuses_installing_source_into_itself(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(INSTALLER),
                "--agent",
                "custom",
                "--target",
                str(ROOT / "skills"),
                "--dry-run",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("源码目录", completed.stderr)


if __name__ == "__main__":
    unittest.main()
