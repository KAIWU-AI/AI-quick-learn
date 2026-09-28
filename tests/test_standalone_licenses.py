"""Standalone contributor distribution must retain existing license provenance."""
import pathlib
import tempfile
import unittest
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]


class StandaloneLicenseTests(unittest.TestCase):
    def test_contributor_archive_preserves_license_and_notice(self):
        skill = ROOT / "skills" / "open-source-contributor"
        expected_notice = (ROOT / "NOTICE.md").read_bytes().split(
            "## AI 基础 Demo 的教学参考".encode()
        )[0].rstrip() + b"\n"
        with tempfile.TemporaryDirectory() as directory:
            archive = pathlib.Path(directory) / "contributor.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                for source in skill.rglob("*"):
                    if source.is_file():
                        bundle.write(source, source.relative_to(skill))
            with zipfile.ZipFile(archive) as bundle:
                self.assertIn("LICENSE", bundle.namelist())
                self.assertIn("NOTICE.md", bundle.namelist())
                self.assertEqual(bundle.read("LICENSE"), (ROOT / "LICENSE").read_bytes())
                self.assertEqual(bundle.read("NOTICE.md"), expected_notice)


if __name__ == "__main__":
    unittest.main()
