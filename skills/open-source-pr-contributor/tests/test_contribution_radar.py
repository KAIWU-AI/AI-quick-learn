from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import datetime as dt
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "contribution_radar.py"
SPEC = importlib.util.spec_from_file_location("contribution_radar", SCRIPT)
assert SPEC and SPEC.loader
radar = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(radar)


class ContributionRadarTests(unittest.TestCase):
    def test_validate_repo_name(self) -> None:
        self.assertEqual(radar.validate_repo_name("owner/repo-name"), "owner/repo-name")
        for invalid in (
            "repo",
            "owner/repo/extra",
            "owner repo/x",
            "https://github.com/o/r",
            "../user",
            "owner/..",
            "-owner/repo",
        ):
            with self.assertRaises(radar.RadarError):
                radar.validate_repo_name(invalid)

    def test_search_terms_reject_credentials_and_query_injection(self) -> None:
        self.assertEqual(radar.validate_search_terms("duplicate initialize"), "duplicate initialize")
        oauth_token = "gho" + "_" + "a" * 30
        for unsafe in (
            "repo:other/project",
            "parser OR auth",
            "token " + oauth_token,
            "https://example.com/error?" + "token=value",
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890",
            'text "quoted"',
        ):
            with self.assertRaises(radar.RadarError):
                radar.validate_search_terms(unsafe)

    def test_redact_known_github_credentials(self) -> None:
        oauth_token = "gho" + "_" + "a" * 30
        fine_grained_token = "github" + "_pat_" + "b" * 30
        raw = (
            "token " + oauth_token + " "
            "Bearer " + fine_grained_token + " "
            "https://user:secret-token@github.com/o/r.git "
            "https://github.com/sso?authorization_request=sensitive-value"
        )
        cleaned = radar.redact(raw)
        self.assertNotIn("secret-token", cleaned)
        self.assertNotIn(oauth_token, cleaned)
        self.assertNotIn(fine_grained_token, cleaned)
        self.assertNotIn("sensitive-value", cleaned)
        self.assertGreaterEqual(cleaned.count("[REDACTED]"), 4)

    def test_repository_signal_score_is_bounded(self) -> None:
        now = dt.datetime.now(dt.timezone.utc)
        metadata = {
            "archived": False,
            "disabled": False,
            "license": {"spdx_id": "MIT"},
            "pushed_at": now.isoformat(),
            "stargazers_count": 20_000,
            "size": 50_000,
        }
        score, reasons = radar.repository_signal_score(metadata)
        self.assertEqual(score, 40)
        self.assertIn("许可证 MIT", reasons)

    def test_issue_signal_prefers_welcomed_unassigned_bug(self) -> None:
        issue = {
            "number": 7,
            "title": "Parser rejects valid input",
            "labels": [
                {"name": "bug"},
                {"name": "good first issue"},
                {"name": "help wanted"},
            ],
            "assignees": [],
            "updatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        score, reasons = radar.issue_signal_score(issue)
        self.assertEqual(score, 60)
        self.assertIn("good first issue", reasons)
        self.assertIn("未分配", reasons)

    def test_load_seed_rejects_duplicate_repositories(self) -> None:
        payload = {
            "repositories": [
                {"repo": "Owner/Repo"},
                {"repo": "owner/repo"},
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "seed.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(radar.RadarError):
                radar.load_seed(path)

    def test_default_seed_is_valid_and_broad(self) -> None:
        data = radar.load_seed(radar.DEFAULT_SEED)
        repositories = data["repositories"]
        self.assertGreaterEqual(len(repositories), 20)
        self.assertEqual(len({item["repo"].lower() for item in repositories}), len(repositories))
        for item in repositories:
            self.assertTrue(radar.validate_repo_name(item["repo"]))
            self.assertIn(item["difficulty"], {"low", "medium", "high"})
            self.assertGreaterEqual(item["stars_snapshot"], 0)

    def test_output_paths_reject_aliases_existing_files_and_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed = root / "seed.json"
            seed.write_text('{"repositories":[{"repo":"owner/repo"}]}', encoding="utf-8")
            output = root / "report.json"
            markdown = root / "report.md"
            radar.validate_output_paths(seed, output, markdown, force=False)
            with self.assertRaises(radar.RadarError):
                radar.validate_output_paths(seed, output, output, force=False)
            with self.assertRaises(radar.RadarError):
                radar.validate_output_paths(seed, seed, markdown, force=False)
            output.write_text("existing", encoding="utf-8")
            with self.assertRaises(radar.RadarError):
                radar.validate_output_paths(seed, output, markdown, force=False)
            output.unlink()
            try:
                output.symlink_to(seed)
            except OSError as exc:
                self.skipTest(f"当前平台不允许创建测试符号链接：{exc}")
            with self.assertRaises(radar.RadarError):
                radar.validate_output_paths(seed, output, markdown, force=True)

    def test_safe_writer_requires_force_and_replaces_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            radar.write_text_safely(path, "first", force=False)
            with self.assertRaises(radar.RadarError):
                radar.write_text_safely(path, "second", force=False)
            radar.write_text_safely(path, "second", force=True)
            self.assertEqual(path.read_text(encoding="utf-8"), "second")

    def test_report_pair_rolls_back_partial_non_force_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "report.json"
            markdown = root / "report.md"
            markdown.write_text("existing", encoding="utf-8")
            with self.assertRaises(radar.RadarError):
                radar.write_report_pair(output, "{}\n", markdown, "# report\n", force=False)
            self.assertFalse(output.exists())
            self.assertEqual(markdown.read_text(encoding="utf-8"), "existing")

    def test_issue_ranking_prefers_recent_issue_when_scores_match(self) -> None:
        old_gh_json = getattr(radar, "gh_json")
        try:
            setattr(
                radar,
                "gh_json",
                lambda args, timeout=45: [
                    {
                        "number": 1,
                        "title": "older",
                        "url": "https://github.com/owner/repo/issues/1",
                        "labels": [{"name": "bug"}],
                        "updatedAt": "2099-01-01T00:00:00Z",
                        "assignees": [],
                    },
                    {
                        "number": 2,
                        "title": "newer",
                        "url": "https://github.com/owner/repo/issues/2",
                        "labels": [{"name": "bug"}],
                        "updatedAt": "2099-02-01T00:00:00Z",
                        "assignees": [],
                    },
                ],
            )
            issues = radar.fetch_issues("owner/repo", limit=2)
        finally:
            setattr(radar, "gh_json", old_gh_json)
        self.assertEqual([item["number"] for item in issues], [2, 1])

    def test_duplicate_search_falls_back_and_filters_repository(self) -> None:
        old_gh_json = getattr(radar, "gh_json")
        old_public_api_json = getattr(radar, "public_api_json")
        try:
            setattr(
                radar,
                "gh_json",
                lambda args, timeout=45: (_ for _ in ()).throw(radar.RadarError("SSO")),
            )
            setattr(
                radar,
                "public_api_json",
                lambda path, timeout=30: {
                    "items": [
                        {
                            "number": 3,
                            "title": "match",
                            "html_url": "https://github.com/owner/repo/issues/3",
                            "repository_url": "https://api.github.com/repos/owner/repo",
                            "state": "open",
                            "updated_at": "2026-09-01T00:00:00Z",
                        },
                    ]
                },
            )
            result = radar.search_duplicates("owner/repo", "duplicate initialize", 5)
        finally:
            setattr(radar, "gh_json", old_gh_json)
            setattr(radar, "public_api_json", old_public_api_json)
        self.assertEqual(result["errors"], {})
        for key in ("open_issues", "closed_issues", "open_prs", "closed_prs"):
            self.assertEqual(len(result[key]), 1)
            self.assertEqual(result[key][0]["repository"], "owner/repo")

    def test_search_results_reject_wrong_repository(self) -> None:
        with self.assertRaises(radar.RadarError):
            radar.normalize_search_results(
                [
                    {
                        "number": 4,
                        "title": "wrong repo",
                        "html_url": "https://github.com/other/repo/issues/4",
                        "repository_url": "https://api.github.com/repos/other/repo",
                        "state": "open",
                    }
                ],
                "owner/repo",
            )

    def test_duplicate_search_records_unknown_when_both_paths_fail(self) -> None:
        old_gh_json = getattr(radar, "gh_json")
        old_public_api_json = getattr(radar, "public_api_json")
        try:
            setattr(
                radar,
                "gh_json",
                lambda args, timeout=45: (_ for _ in ()).throw(radar.RadarError("auth failed")),
            )
            setattr(
                radar,
                "public_api_json",
                lambda path, timeout=30: (_ for _ in ()).throw(radar.RadarError("public failed")),
            )
            result = radar.search_duplicates("owner/repo", "duplicate initialize", 5)
        finally:
            setattr(radar, "gh_json", old_gh_json)
            setattr(radar, "public_api_json", old_public_api_json)
        self.assertEqual(len(result["errors"]), 4)
        self.assertTrue(all(result[key] == [] for key in result["errors"]))

    def test_duplicate_cli_returns_nonzero_for_unknown_results(self) -> None:
        old_search_duplicates = getattr(radar, "search_duplicates")
        try:
            setattr(
                radar,
                "search_duplicates",
                lambda repo, terms, limit: {
                    "repo": repo,
                    "terms": terms,
                    "open_issues": [],
                    "closed_issues": [],
                    "open_prs": [],
                    "closed_prs": [],
                    "errors": {"open_prs": "network unavailable"},
                },
            )
            with redirect_stdout(io.StringIO()):
                code = radar.main(["duplicates", "owner/repo", "parser failure"])
        finally:
            setattr(radar, "search_duplicates", old_search_duplicates)
        self.assertEqual(code, 2)

    def test_markdown_report_does_not_need_private_paths(self) -> None:
        report = {
            "generated_at": "2026-09-26T00:00:00+00:00",
            "warning": "先复现，再贡献。",
            "repositories": [
                {
                    "repo": "owner/repo",
                    "url": "https://github.com/owner/repo",
                    "language": "Python",
                    "stars": 100,
                    "license": "MIT",
                    "repository_signal_score": 30,
                    "best_issue_signal_score": 45,
                    "issue_leads": [
                        {
                            "number": 1,
                            "title": "Broken parser",
                            "url": "https://github.com/owner/repo/issues/1",
                            "labels": ["bug"],
                            "assignees": [],
                            "signal_score": 45,
                        }
                    ],
                }
            ],
            "errors": [],
        }
        text = radar.markdown_report(report)
        self.assertIn("owner/repo", text)
        self.assertIn("#1 Broken parser", text)
        self.assertNotIn("/" + "Users/", text)
        self.assertNotIn("[REDACTED]", text)

    def test_scan_keeps_api_failures_unknown(self) -> None:
        original = getattr(radar, "inspect_repository")
        try:
            setattr(
                radar,
                "inspect_repository",
                lambda repo, max_issues: (_ for _ in ()).throw(radar.RadarError("rate limited")),
            )
            report = radar.scan(
                {"snapshot_date": "2026-09-26", "repositories": [{"repo": "owner/repo"}]},
                max_repos=1,
                max_issues=5,
                language=None,
            )
        finally:
            setattr(radar, "inspect_repository", original)
        self.assertEqual(report["repositories"], [])
        self.assertEqual(report["errors"][0]["repo"], "owner/repo")
        self.assertIn("rate limited", report["errors"][0]["error"])

    def test_scan_cli_does_not_write_when_every_repository_fails(self) -> None:
        old_scan = getattr(radar, "scan")
        try:
            setattr(
                radar,
                "scan",
                lambda seed, max_repos, max_issues, language: {
                    "schema_version": 1,
                    "generated_at": "2026-09-26T00:00:00+00:00",
                    "source_snapshot_date": "2026-09-26",
                    "warning": "unknown",
                    "repositories": [],
                    "errors": [{"repo": "owner/repo", "error": "network unavailable"}],
                },
            )
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                seed = root / "seed.json"
                output = root / "report.json"
                markdown = root / "report.md"
                seed.write_text('{"repositories":[{"repo":"owner/repo"}]}', encoding="utf-8")
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    code = radar.main(
                        [
                            "scan",
                            "--seed",
                            str(seed),
                            "--max-repos",
                            "1",
                            "--output",
                            str(output),
                            "--markdown",
                            str(markdown),
                        ]
                    )
                self.assertEqual(code, 2)
                self.assertFalse(output.exists())
                self.assertFalse(markdown.exists())
        finally:
            setattr(radar, "scan", old_scan)


if __name__ == "__main__":
    unittest.main()
