from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import datetime as dt
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
        skill_repositories = [item for item in repositories if item["category"] == "Agent Skill"]
        self.assertGreaterEqual(len(skill_repositories), 6)
        removed_heavy_repositories = {
            "openclaw/openclaw",
            "pydantic/pydantic",
            "astral-sh/ruff",
            "langchain-ai/langchain",
            "run-llama/llama_index",
            "huggingface/transformers",
            "openai/codex",
            "go-gitea/gitea",
        }
        self.assertTrue(
            removed_heavy_repositories.isdisjoint(item["repo"] for item in repositories)
        )
        for item in repositories:
            self.assertTrue(radar.validate_repo_name(item["repo"]))
            self.assertIn(item["difficulty"], {"low", "medium", "high"})
            self.assertGreaterEqual(item["stars_snapshot"], 0)
            self.assertIn(item["setup"]["level"], {"light", "moderate", "heavy"})
            self.assertIsInstance(item["setup"]["required_commands"], list)

    def test_local_fit_rejects_missing_tools_and_platforms(self) -> None:
        environment = {
            "platform": "macos",
            "architecture": "arm64",
            "commands": {"python3": True, "node": False, "go": False},
        }
        missing_tool = radar.evaluate_local_fit(
            {
                "setup": {
                    "level": "moderate",
                    "required_commands": ["node"],
                    "platforms": ["linux", "macos", "windows"],
                }
            },
            environment,
        )
        self.assertFalse(missing_tool["compatible"])
        self.assertIn("缺少命令：node", missing_tool["blockers"])

        wrong_platform = radar.evaluate_local_fit(
            {
                "setup": {
                    "level": "light",
                    "required_commands": ["python3"],
                    "platforms": ["linux"],
                }
            },
            environment,
        )
        self.assertFalse(wrong_platform["compatible"])
        self.assertIn("不支持当前平台 macos", wrong_platform["blockers"])

    def test_detect_environment_accepts_python_command_alias(self) -> None:
        def fake_which(command: str) -> str | None:
            return f"/usr/bin/{command}" if command in {"git", "gh", "python"} else None

        with mock.patch.object(radar.shutil, "which", side_effect=fake_which):
            environment = radar.detect_local_environment()
        self.assertTrue(environment["commands"]["python3"])

    def test_recommendation_prefers_runtime_bug_over_metadata_cleanup(self) -> None:
        common = {
            "archived": False,
            "disabled": False,
            "license": "MIT",
            "repository_signal_score": 40,
            "local_fit": {"compatible": True, "score": 30, "reasons": ["本机依赖齐全"]},
            "seed": {"difficulty": "low"},
        }
        repositories = [
            {
                **common,
                "repo": "owner/metadata",
                "issue_leads": [
                    {
                        "number": 1,
                        "title": "Missing LICENSE file",
                        "url": "https://github.com/owner/metadata/issues/1",
                        "labels": ["bug"],
                        "assignees": [],
                        "linked_pull_requests": [],
                        "signal_score": 30,
                        "signal_reasons": ["bug"],
                    }
                ],
            },
            {
                **common,
                "repo": "owner/runtime",
                "issue_leads": [
                    {
                        "number": 2,
                        "title": "Installer does not record local path",
                        "url": "https://github.com/owner/runtime/issues/2",
                        "labels": ["bug"],
                        "assignees": [],
                        "linked_pull_requests": [],
                        "signal_score": 30,
                        "signal_reasons": ["bug"],
                    }
                ],
            },
        ]
        result = radar.select_recommended_opportunity(repositories)
        self.assertEqual(result["repo"], "owner/runtime")

    def test_recommendation_skips_issue_with_linked_pull_request(self) -> None:
        repositories = [
            {
                "repo": "owner/skills",
                "archived": False,
                "disabled": False,
                "license": "MIT",
                "repository_signal_score": 40,
                "local_fit": {"compatible": True, "score": 30, "reasons": []},
                "seed": {"difficulty": "low", "category": "Agent Skill"},
                "issue_leads": [
                    {
                        "number": 1,
                        "title": "Installer fails",
                        "url": "https://github.com/owner/skills/issues/1",
                        "labels": ["bug"],
                        "assignees": [],
                        "linked_pull_requests": ["https://github.com/owner/skills/pull/2"],
                        "signal_score": 60,
                        "signal_reasons": ["bug"],
                    },
                    {
                        "number": 3,
                        "title": "Validator rejects valid skill",
                        "url": "https://github.com/owner/skills/issues/3",
                        "labels": ["bug"],
                        "assignees": [],
                        "linked_pull_requests": [],
                        "signal_score": 30,
                        "signal_reasons": ["bug"],
                    },
                ],
            }
        ]
        result = radar.select_recommended_opportunity(repositories)
        self.assertEqual(result["issue"]["number"], 3)

    def test_recommendation_prefers_skill_repo_when_scores_are_close(self) -> None:
        def repository(repo: str, category: str, repo_score: int) -> dict[str, object]:
            return {
                "repo": repo,
                "archived": False,
                "disabled": False,
                "license": "MIT",
                "repository_signal_score": repo_score,
                "local_fit": {"compatible": True, "score": 30, "reasons": []},
                "seed": {"difficulty": "low", "category": category},
                "issue_leads": [
                    {
                        "number": 1,
                        "title": "Validator fails for valid input",
                        "url": f"https://github.com/{repo}/issues/1",
                        "labels": ["bug"],
                        "assignees": [],
                        "linked_pull_requests": [],
                        "signal_score": 30,
                        "signal_reasons": ["bug"],
                    }
                ],
            }

        result = radar.select_recommended_opportunity(
            [repository("owner/library", "网络库", 40), repository("owner/skills", "Agent Skill", 35)]
        )
        self.assertEqual(result["repo"], "owner/skills")

    def test_scan_prioritizes_easy_local_fit_before_request_limit(self) -> None:
        seed = {
            "repositories": [
                {
                    "repo": "owner/heavy",
                    "category": "机器学习",
                    "difficulty": "high",
                    "setup": {
                        "level": "heavy",
                        "required_commands": ["cargo"],
                        "platforms": ["linux", "macos", "windows"],
                    },
                },
                {
                    "repo": "owner/skill",
                    "category": "Agent Skill",
                    "difficulty": "low",
                    "setup": {
                        "level": "light",
                        "required_commands": ["python3"],
                        "platforms": ["linux", "macos", "windows"],
                    },
                },
            ]
        }
        environment = {
            "platform": "macos",
            "architecture": "arm64",
            "commands": {"python3": True, "cargo": False},
        }
        inspected: list[str] = []

        def fake_inspect(repo: str, max_issues: int) -> dict[str, object]:
            inspected.append(repo)
            return {
                "repo": repo,
                "description": "test",
                "url": f"https://github.com/{repo}",
                "language": "Python",
                "license": "MIT",
                "stars": 100,
                "forks": 10,
                "open_issues_and_prs": 1,
                "default_branch": "main",
                "pushed_at": "2099-01-01T00:00:00Z",
                "size_kb": 100,
                "archived": False,
                "disabled": False,
                "repository_signal_score": 32,
                "repository_signal_reasons": [],
                "issue_leads": [
                    {
                        "number": 9,
                        "title": "Fix skill validator",
                        "url": f"https://github.com/{repo}/issues/9",
                        "labels": ["bug"],
                        "updated_at": "2099-01-01T00:00:00Z",
                        "assignees": [],
                        "linked_pull_requests": [],
                        "signal_score": 30,
                        "signal_reasons": ["bug"],
                    }
                ],
            }

        with mock.patch.object(radar, "inspect_repository", side_effect=fake_inspect):
            report = radar.scan(seed, max_repos=1, max_issues=5, language=None, environment=environment)

        self.assertEqual(inspected, ["owner/skill"])
        self.assertEqual(report["recommended_opportunity"]["repo"], "owner/skill")
        self.assertEqual(report["recommended_opportunity"]["issue"]["number"], 9)
        self.assertEqual(report["recommended_opportunity"]["status"], "needs_verification")

    def test_scan_detects_custom_seed_commands(self) -> None:
        seed = {
            "repositories": [
                {
                    "repo": "owner/custom",
                    "category": "Agent Skill",
                    "difficulty": "low",
                    "setup": {
                        "level": "light",
                        "required_commands": ["custom-validator"],
                        "platforms": ["macos"],
                    },
                }
            ]
        }
        inspected: list[str] = []

        def fake_inspect(repo: str, max_issues: int) -> dict[str, object]:
            inspected.append(repo)
            return {
                "repo": repo,
                "license": "MIT",
                "archived": False,
                "disabled": False,
                "repository_signal_score": 30,
                "repository_signal_reasons": [],
                "issue_leads": [],
            }

        with mock.patch.object(
            radar,
            "detect_local_environment",
            return_value={"platform": "macos", "architecture": "arm64", "commands": {}},
        ), mock.patch.object(
            radar.shutil,
            "which",
            side_effect=lambda command: "/usr/local/bin/custom-validator"
            if command == "custom-validator"
            else None,
        ), mock.patch.object(radar, "inspect_repository", side_effect=fake_inspect):
            report = radar.scan(seed, max_repos=1, max_issues=1, language=None)

        self.assertEqual(inspected, ["owner/custom"])
        self.assertTrue(report["local_environment"]["commands"]["custom-validator"])

    def test_markdown_report_highlights_exactly_one_recommendation(self) -> None:
        report = {
            "generated_at": "2026-09-27T00:00:00+00:00",
            "warning": "先复现，再贡献。",
            "local_environment": {
                "platform": "macos",
                "architecture": "arm64",
                "commands": {"python3": True, "node": True},
            },
            "recommended_opportunity": {
                "status": "needs_verification",
                "repo": "owner/skills",
                "issue": {
                    "number": 7,
                    "title": "Fix validator",
                    "url": "https://github.com/owner/skills/issues/7",
                },
                "selection_score": 88,
                "why": ["本机依赖齐全", "轻量仓库"],
                "next_step": "先阅读完整 Issue 和贡献政策，再在当前默认分支复现。",
            },
            "repositories": [],
            "errors": [],
        }
        text = radar.markdown_report(report)
        self.assertEqual(text.count("## 建议优先验证的 1 个机会"), 1)
        self.assertIn("owner/skills #7", text)
        self.assertIn("macos/arm64", text)

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

    def test_fetch_issues_keeps_recent_unlabeled_runtime_bug(self) -> None:
        old_gh_json = getattr(radar, "gh_json")
        try:
            setattr(
                radar,
                "gh_json",
                lambda args, timeout=45: [
                    {
                        "number": 5,
                        "title": "Installer crashes when the source path contains spaces",
                        "url": "https://github.com/owner/repo/issues/5",
                        "labels": [],
                        "updatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
                        "assignees": [],
                        "closedByPullRequestsReferences": [],
                    }
                ],
            )
            issues = radar.fetch_issues("owner/repo", limit=5)
        finally:
            setattr(radar, "gh_json", old_gh_json)
        self.assertEqual([item["number"] for item in issues], [5])
        self.assertIn("标题包含可复现症状", issues[0]["signal_reasons"])

    def test_fetch_issues_filters_linked_prs_before_limit_and_keeps_label_search(self) -> None:
        calls: list[list[str]] = []
        linked = [
            {
                "number": number,
                "title": f"Bug {number}",
                "url": f"https://github.com/owner/repo/issues/{number}",
                "labels": [{"name": "bug"}],
                "updatedAt": "2099-01-01T00:00:00Z",
                "assignees": [],
                "closedByPullRequestsReferences": [
                    {"url": f"https://github.com/owner/repo/pull/{number}"}
                ],
            }
            for number in range(1, 31)
        ]
        eligible = {
            "number": 31,
            "title": "Parser fails on valid input",
            "url": "https://github.com/owner/repo/issues/31",
            "labels": [],
            "updatedAt": "2099-01-01T00:00:00Z",
            "assignees": [],
            "closedByPullRequestsReferences": [],
        }

        def fake_gh_json(args: list[str], timeout: int = 45) -> list[dict[str, object]]:
            calls.append(args)
            requested_limit = int(args[args.index("--limit") + 1])
            return [*linked, eligible][:requested_limit]

        with mock.patch.object(radar, "gh_json", side_effect=fake_gh_json):
            issues = radar.fetch_issues("owner/repo", limit=5)

        self.assertEqual([item["number"] for item in issues], [31])
        searches = [args[args.index("--search") + 1] for args in calls]
        self.assertTrue(any("label:" in query for query in searches))
        self.assertIn("sort:updated-desc", searches)

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
