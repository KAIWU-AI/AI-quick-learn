#!/usr/bin/env python3
"""开源贡献候选扫描器。

所有子命令对 GitHub 远端只读：检查环境、读取公开仓库元数据、筛选
issue、搜索重复工作。scan 会在本地写报告；脚本不会 fork、push、评论、
创建 issue 或 PR。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SEED = SCRIPT_DIR.parent / "references" / "repository-pool.json"
GITHUB_API = "https://api.github.com"
INTERESTING_LABELS = {
    "bug",
    "good first issue",
    "help wanted",
    "ready for work",
    "contributions welcome",
    "starter",
}
ACTIONABLE_TITLE_TERMS = (
    "bug",
    "crash",
    "error",
    "fail",
    "broken",
    "incorrect",
    "does not",
    "doesn't",
    "cannot",
    "can't",
    "ignored",
    "missing",
    "regression",
)
TOKEN_PATTERNS = (
    re.compile(r"\b(?:gh[opusr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"(?i)\b(Bearer|token)\s+[A-Za-z0-9._~+\-/=]{12,}"),
    re.compile(r"https://[^\s/:]+:[^\s/@]+@github\.com"),
    re.compile(r"(?i)(authorization_request|access_token|token|signature|sig)=([^&\s]+)"),
)
OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
SEARCH_QUALIFIER_RE = re.compile(
    r"(?i)(?:^|\s)(?:repo|org|user|is|state|label|in|sort|language|type):"
)
SEARCH_BOOLEAN_RE = re.compile(r"(?i)(?:^|\s)(?:AND|OR|NOT)(?:\s|$)")
KNOWN_COMMANDS = (
    "git",
    "gh",
    "python3",
    "uv",
    "node",
    "npm",
    "pnpm",
    "bun",
    "cargo",
    "rustc",
    "go",
    "dotnet",
    "jq",
    "curl",
)
SETUP_LEVEL_SCORE = {"light": 22, "moderate": 14, "heavy": 4}
DIFFICULTY_SCORE = {"low": 10, "medium": 5, "high": 0}


class RadarError(RuntimeError):
    """可预期、适合直接展示给用户的错误。"""


def configure_utf8_stdio() -> None:
    """Keep Chinese CLI output usable when Windows redirects output."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")


def redact(text: str) -> str:
    """清理常见 GitHub 凭据，避免错误输出泄漏 token。"""
    cleaned = text
    for pattern in TOKEN_PATTERNS:
        cleaned = pattern.sub("[REDACTED]", cleaned)
    return cleaned


def validate_repo_name(repo: str) -> str:
    if repo.count("/") != 1:
        raise RadarError(f"非法仓库名：{repo!r}，应为 OWNER/REPO")
    owner, repository = repo.split("/", 1)
    if not OWNER_RE.fullmatch(owner) or not REPOSITORY_RE.fullmatch(repository):
        raise RadarError(f"非法仓库名：{repo!r}，应为 OWNER/REPO")
    if repository in {".", ".."}:
        raise RadarError(f"非法仓库名：{repo!r}，不允许路径段穿越")
    return repo


def validate_search_terms(terms: str) -> str:
    terms = terms.strip()
    if not terms or len(terms) > 200:
        raise RadarError("搜索词不能为空，且不得超过 200 个字符")
    if redact(terms) != terms:
        raise RadarError("搜索词疑似包含凭据；请改用不含秘密的错误摘要或符号名")
    if any(ord(char) < 32 for char in terms) or '"' in terms:
        raise RadarError("搜索词不能包含控制字符或双引号")
    if "://" in terms or any(char in terms for char in ("@", "=", "?", "&")):
        raise RadarError("搜索词不能包含 URL、账号或查询参数；请改用简短错误摘要")
    if re.search(r"\b[A-Za-z0-9_-]{32,}\b", terms):
        raise RadarError("搜索词包含疑似高熵标识符；请先移除凭据和私有 ID")
    if SEARCH_QUALIFIER_RE.search(terms) or SEARCH_BOOLEAN_RE.search(terms):
        raise RadarError("搜索词不能包含 GitHub 查询限定符或布尔操作符")
    return terms


def run_command(args: list[str], timeout: int = 45) -> str:
    """不用 shell 执行命令，返回 stdout。"""
    env = os.environ.copy()
    env["GH_PROMPT_DISABLED"] = "1"
    try:
        completed = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
        )
    except FileNotFoundError as exc:
        raise RadarError(f"找不到命令：{args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RadarError(f"命令超时：{' '.join(args[:3])}") from exc
    if completed.returncode != 0:
        detail = redact((completed.stderr or completed.stdout).strip())
        raise RadarError(f"命令失败（{completed.returncode}）：{detail[:800]}")
    return completed.stdout


def gh_json(args: list[str], timeout: int = 45) -> Any:
    raw = run_command(["gh", *args], timeout=timeout)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RadarError("GitHub CLI 返回了无效 JSON") from exc


def public_api_json(path: str, timeout: int = 30) -> Any:
    """认证请求受组织 SSO 限制时，回退到公开只读 API。"""
    request = urllib.request.Request(
        f"{GITHUB_API}/{path.lstrip('/')}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "AI-quick-learn-contribution-radar",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RadarError(f"公开 GitHub API 读取失败：{redact(str(exc))}") from exc


def api_json(path: str, timeout: int = 45) -> Any:
    try:
        return gh_json(["api", "--method", "GET", path], timeout=timeout)
    except RadarError as authenticated_error:
        try:
            return public_api_json(path, timeout=min(timeout, 30))
        except RadarError as public_error:
            raise RadarError(
                f"GitHub API 读取失败；认证与公开回退均不可用。"
                f"认证错误：{authenticated_error}；公开错误：{public_error}"
            ) from public_error


def parse_time(value: str | None) -> dt.datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def age_days(value: str | None, now: dt.datetime | None = None) -> int | None:
    parsed = parse_time(value)
    if parsed is None:
        return None
    now = now or dt.datetime.now(dt.timezone.utc)
    return max(0, (now - parsed).days)


def time_rank(value: str | None) -> tuple[int, int, int, int, int, int]:
    parsed = parse_time(value)
    if parsed is None:
        return (0, 0, 0, 0, 0, 0)
    utc = parsed.astimezone(dt.timezone.utc)
    return (utc.year, utc.month, utc.day, utc.hour, utc.minute, utc.second)


def nonnegative_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)


def normalize_platform(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"darwin", "mac", "macos"}:
        return "macos"
    if normalized.startswith("win"):
        return "windows"
    if normalized == "linux":
        return "linux"
    return normalized or "unknown"


def detect_local_environment() -> dict[str, Any]:
    """Detect only non-sensitive capabilities used for local-fit ranking."""
    commands = {command: bool(shutil.which(command)) for command in KNOWN_COMMANDS}
    commands["python3"] = commands["python3"] or any(
        shutil.which(alias) for alias in ("python", "py")
    )
    return {
        "platform": normalize_platform(platform.system()),
        "architecture": platform.machine().lower() or "unknown",
        "python_version": (
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        ),
        "commands": commands,
    }


def evaluate_local_fit(
    seed_item: dict[str, Any], environment: dict[str, Any]
) -> dict[str, Any]:
    setup = seed_item.get("setup") or {}
    level = str(setup.get("level") or "moderate").lower()
    required_commands = [str(item) for item in setup.get("required_commands") or []]
    platforms = [normalize_platform(str(item)) for item in setup.get("platforms") or []]
    current_platform = normalize_platform(str(environment.get("platform") or "unknown"))
    available_commands = environment.get("commands") or {}

    blockers: list[str] = []
    missing_commands = [
        command for command in required_commands if not available_commands.get(command, False)
    ]
    blockers.extend(f"缺少命令：{command}" for command in missing_commands)
    if platforms and current_platform not in platforms:
        blockers.append(f"不支持当前平台 {current_platform}")

    compatible = not blockers
    score = SETUP_LEVEL_SCORE.get(level, 0)
    if compatible:
        score += 8
    else:
        score = 0
    reasons = [f"{level} 级本地准备"]
    if compatible:
        reasons.append("本机必需命令齐全")
    return {
        "compatible": compatible,
        "score": min(score, 30),
        "setup_level": level,
        "required_commands": required_commands,
        "missing_commands": missing_commands,
        "blockers": blockers,
        "reasons": reasons,
    }


def candidate_priority(
    seed_item: dict[str, Any], environment: dict[str, Any]
) -> tuple[int, int, int, str]:
    fit = evaluate_local_fit(seed_item, environment)
    difficulty = str(seed_item.get("difficulty") or "high").lower()
    skill_rank = 0 if seed_item.get("category") == "Agent Skill" else 1
    return (
        0 if fit["compatible"] else 1,
        -fit["score"] - DIFFICULTY_SCORE.get(difficulty, 0),
        skill_rank,
        str(seed_item.get("repo") or "").lower(),
    )


def extend_environment_for_seed(
    environment: dict[str, Any], seed: dict[str, Any]
) -> dict[str, Any]:
    extended = {**environment, "commands": dict(environment.get("commands") or {})}
    for item in seed.get("repositories") or []:
        setup = item.get("setup") if isinstance(item, dict) else None
        if not isinstance(setup, dict):
            continue
        for command in setup.get("required_commands") or []:
            if command not in extended["commands"]:
                extended["commands"][command] = bool(shutil.which(command))
    return extended


def normalize_license(metadata: dict[str, Any]) -> str | None:
    license_data = metadata.get("license")
    if isinstance(license_data, dict):
        return license_data.get("spdx_id")
    if isinstance(license_data, str):
        return license_data
    return None


def repository_signal_score(metadata: dict[str, Any]) -> tuple[int, list[str]]:
    """只用于排序的仓库线索分，不代表可以直接贡献。满分 40。"""
    score = 0
    reasons: list[str] = []
    if not metadata.get("archived") and not metadata.get("disabled"):
        score += 5
    license_id = normalize_license(metadata)
    if license_id and license_id not in {"NOASSERTION", "Other"}:
        score += 10
        reasons.append(f"许可证 {license_id}")
    pushed_days = age_days(metadata.get("pushed_at"))
    if pushed_days is not None and pushed_days <= 14:
        score += 10
        reasons.append("近 14 天活跃")
    elif pushed_days is not None and pushed_days <= 30:
        score += 5
        reasons.append("近 30 天活跃")
    stars = nonnegative_int(metadata.get("stargazers_count"))
    if stars >= 10_000:
        score += 8
        reasons.append("高关注项目")
    elif stars >= 2_000:
        score += 5
    size = nonnegative_int(metadata.get("size"))
    if 0 < size <= 100_000:
        score += 7
        reasons.append("仓库规模适合聚焦测试")
    elif 0 < size <= 500_000:
        score += 4
    return min(score, 40), reasons


def label_names(issue: dict[str, Any]) -> set[str]:
    labels = issue.get("labels") or []
    if not isinstance(labels, list):
        raise RadarError("Issue labels 字段不是数组")
    names: set[str] = set()
    for label in labels:
        if isinstance(label, dict):
            name = label.get("name")
        elif isinstance(label, str):
            name = label
        else:
            raise RadarError("Issue label 数据格式异常")
        if name is not None and not isinstance(name, str):
            raise RadarError("Issue label 名称不是字符串")
        if name:
            names.add(name.strip().lower())
    return names


def issue_signal_score(issue: dict[str, Any]) -> tuple[int, list[str]]:
    """只用于排序的 issue 线索分，不替代复现和重复项检查。满分 60。"""
    score = 0
    reasons: list[str] = []
    labels = label_names(issue)
    if "good first issue" in labels:
        score += 25
        reasons.append("good first issue")
    if "help wanted" in labels:
        score += 20
        reasons.append("help wanted")
    if "ready for work" in labels or "contributions welcome" in labels:
        score += 20
        reasons.append("维护者标记可贡献")
    if "starter" in labels:
        score += 15
        reasons.append("starter")
    if "bug" in labels:
        score += 10
        reasons.append("bug")
    title = str(issue.get("title") or "").lower()
    if any(term in title for term in ACTIONABLE_TITLE_TERMS):
        score += 15
        reasons.append("标题包含可复现症状")
    if not issue.get("assignees"):
        score += 10
        reasons.append("未分配")
    updated_days = age_days(issue.get("updatedAt") or issue.get("updated_at"))
    if updated_days is not None and updated_days <= 30:
        score += 10
        reasons.append("近 30 天更新")
    return min(score, 60), reasons


def normalize_issue(issue: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(issue, dict):
        raise RadarError("Issue 数据不是对象")
    number = nonnegative_int(issue.get("number"))
    if number <= 0:
        raise RadarError("Issue 数据缺少有效编号")
    labels = sorted(label_names(issue))
    assignees = issue.get("assignees") or []
    if not isinstance(assignees, list):
        raise RadarError("Issue assignees 字段不是数组")
    normalized_assignees: list[str] = []
    for item in assignees:
        if not isinstance(item, dict) or not isinstance(item.get("login"), str):
            raise RadarError("Issue assignee 数据格式异常")
        normalized_assignees.append(item["login"])
    title = issue.get("title")
    url = issue.get("url") or issue.get("html_url")
    if not isinstance(title, str) or not isinstance(url, str):
        raise RadarError("Issue 缺少有效标题或 URL")
    linked_pull_requests: list[str] | None = None
    if "closedByPullRequestsReferences" in issue:
        raw_links = issue.get("closedByPullRequestsReferences")
        if not isinstance(raw_links, list):
            raise RadarError("Issue 关联 PR 字段不是数组")
        linked_pull_requests = []
        for pull_request in raw_links:
            if not isinstance(pull_request, dict) or not isinstance(
                pull_request.get("url"), str
            ):
                raise RadarError("Issue 关联 PR 数据格式异常")
            linked_pull_requests.append(pull_request["url"])
    return {
        "number": number,
        "title": title,
        "url": url,
        "labels": labels,
        "updated_at": issue.get("updatedAt") or issue.get("updated_at"),
        "assignees": [name for name in normalized_assignees if name],
        "linked_pull_requests": linked_pull_requests,
    }


def fetch_repository(repo: str) -> dict[str, Any]:
    repo = validate_repo_name(repo)
    metadata = api_json(f"repos/{repo}")
    if not isinstance(metadata, dict) or "full_name" not in metadata:
        raise RadarError(f"仓库元数据格式异常：{repo}")
    if str(metadata["full_name"]).lower() != repo.lower():
        raise RadarError(f"仓库元数据与请求目标不一致：{repo}")
    return metadata


def public_issue_search(repo: str, search_terms: str, limit: int) -> list[dict[str, Any]]:
    """Read up to GitHub Search's 1,000-result cap in 100-item pages."""
    items: list[dict[str, Any]] = []
    per_page = 100
    for page in range(1, min(10, (limit + per_page - 1) // per_page) + 1):
        public_terms = f"repo:{repo} is:issue is:open {search_terms}".strip()
        query = urllib.parse.quote(public_terms)
        search_result = api_json(
            f"search/issues?q={query}&sort=updated&order=desc&per_page={per_page}&page={page}",
            timeout=60,
        )
        if not isinstance(search_result, dict) or not isinstance(
            search_result.get("items"), list
        ):
            raise RadarError(f"Issue 搜索结果格式异常：{repo}")
        page_items = search_result["items"]
        items.extend(page_items)
        if len(page_items) < per_page or len(items) >= limit:
            break
    return items[:limit]


def fetch_issues(repo: str, limit: int = 10) -> list[dict[str, Any]]:
    repo = validate_repo_name(repo)
    # GitHub issue search exposes at most 1,000 results. Ask gh to paginate to
    # that cap, then remove assigned/linked/non-actionable rows before applying
    # the caller's small output limit.
    request_limit = 1000
    label_query = (
        '(label:"good first issue" OR label:"help wanted" OR label:bug '
        'OR label:"ready for work" OR label:"contributions welcome" '
        'OR label:starter)'
    )
    raw_by_number: dict[int, dict[str, Any]] = {}
    for search_terms in (label_query, ""):
        gh_search = f"sort:updated-desc {search_terms}".strip()
        try:
            raw = gh_json(
                [
                    "issue",
                    "list",
                    "-R",
                    repo,
                    "--state",
                    "open",
                    "--limit",
                    str(request_limit),
                    "--search",
                    gh_search,
                    "--json",
                    "number,title,url,labels,updatedAt,assignees,closedByPullRequestsReferences",
                ],
                timeout=60,
            )
        except RadarError:
            raw = public_issue_search(repo, search_terms, request_limit)
        if not isinstance(raw, list):
            raise RadarError(f"Issue 列表格式异常：{repo}")
        for item in raw:
            normalized = normalize_issue(item)
            raw_by_number[normalized["number"]] = normalized

    interesting = [
        issue
        for issue in raw_by_number.values()
        if not issue.get("linked_pull_requests")
        and (
            label_names(issue) & INTERESTING_LABELS
            or any(term in issue["title"].lower() for term in ACTIONABLE_TITLE_TERMS)
        )
    ]
    ranked = []
    for issue in interesting:
        score, reasons = issue_signal_score(issue)
        ranked.append({**issue, "signal_score": score, "signal_reasons": reasons})
    ranked.sort(
        key=lambda item: (
            -item["signal_score"],
            tuple(-part for part in time_rank(item.get("updated_at"))),
            item["number"],
        )
    )
    return ranked[:limit]


def load_seed(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RadarError(f"候选池文件不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise RadarError(f"候选池 JSON 无效：{path}") from exc
    if not isinstance(data, dict):
        raise RadarError("候选池顶层必须是 JSON 对象")
    repositories = data.get("repositories")
    if not isinstance(repositories, list) or not repositories:
        raise RadarError("候选池必须包含非空 repositories 数组")
    seen: set[str] = set()
    for item in repositories:
        if not isinstance(item, dict) or "repo" not in item:
            raise RadarError("候选池中的每项都必须是包含 repo 的对象")
        repo = validate_repo_name(str(item["repo"]))
        if repo.lower() in seen:
            raise RadarError(f"候选池仓库重复：{repo}")
        seen.add(repo.lower())
        difficulty = item.get("difficulty")
        if difficulty not in {"low", "medium", "high"}:
            raise RadarError(f"候选池 difficulty 无效：{repo}")
        setup = item.get("setup")
        if not isinstance(setup, dict):
            raise RadarError(f"候选池 setup 无效：{repo}")
        if setup.get("level") not in SETUP_LEVEL_SCORE:
            raise RadarError(f"候选池 setup.level 无效：{repo}")
        required_commands = setup.get("required_commands")
        if not isinstance(required_commands, list) or not all(
            isinstance(command, str) and command for command in required_commands
        ):
            raise RadarError(f"候选池 required_commands 无效：{repo}")
        platforms = setup.get("platforms")
        if not isinstance(platforms, list) or not platforms:
            raise RadarError(f"候选池 platforms 无效：{repo}")
    return data


def inspect_repository(repo: str, max_issues: int) -> dict[str, Any]:
    metadata = fetch_repository(repo)
    score, reasons = repository_signal_score(metadata)
    issues = fetch_issues(repo, max_issues)
    return {
        "repo": metadata["full_name"],
        "description": metadata.get("description"),
        "url": metadata.get("html_url"),
        "language": metadata.get("language"),
        "license": normalize_license(metadata),
        "stars": nonnegative_int(metadata.get("stargazers_count")),
        "forks": nonnegative_int(metadata.get("forks_count")),
        "open_issues_and_prs": nonnegative_int(metadata.get("open_issues_count")),
        "default_branch": metadata.get("default_branch"),
        "pushed_at": metadata.get("pushed_at"),
        "size_kb": nonnegative_int(metadata.get("size")),
        "archived": bool(metadata.get("archived")),
        "disabled": bool(metadata.get("disabled")),
        "repository_signal_score": score,
        "repository_signal_reasons": reasons,
        "issue_leads": issues,
    }


def issue_scope_score(issue: dict[str, Any]) -> tuple[int, list[str]]:
    """Prefer reproducible behavior bugs over repository metadata chores."""
    title = str(issue.get("title") or "").lower()
    labels = set(issue.get("labels") or [])
    adjustment = 0
    reasons: list[str] = []
    if "bug" in labels:
        adjustment += 15
        reasons.append("行为缺陷")
    runtime_terms = (
        *ACTIONABLE_TITLE_TERMS,
        "install",
        "validator",
        "symlink",
        "local path",
        "state",
    )
    if any(term in title for term in runtime_terms):
        adjustment += 10
        reasons.append("标题包含可复现的运行时症状")
    metadata_terms = (
        "missing license",
        "readme typo",
        "badge",
        "spelling",
        "re-index",
        "re-audit",
        "community video",
        "skills.sh",
    )
    if any(term in title for term in metadata_terms):
        adjustment -= 50
        reasons.append("低价值元数据或排版事项降权")
    return adjustment, reasons


def select_recommended_opportunity(
    repositories: list[dict[str, Any]],
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for repository in repositories:
        fit = repository.get("local_fit") or {}
        if not fit.get("compatible") or repository.get("archived") or repository.get("disabled"):
            continue
        if repository.get("license") in {None, "NOASSERTION", "Other"}:
            continue
        difficulty = str((repository.get("seed") or {}).get("difficulty") or "high")
        category = str((repository.get("seed") or {}).get("category") or "")
        for issue in repository.get("issue_leads") or []:
            if issue.get("assignees"):
                continue
            linked_pull_requests = issue.get("linked_pull_requests")
            if linked_pull_requests is None or linked_pull_requests:
                continue
            labels = set(issue.get("labels") or [])
            if "breaking api change" in labels:
                continue
            updated_days = age_days(issue.get("updated_at"))
            if updated_days is not None and updated_days > 180:
                continue
            scope_adjustment, scope_reasons = issue_scope_score(issue)
            if scope_adjustment < 0:
                continue
            selection_score = (
                nonnegative_int(repository.get("repository_signal_score"))
                + nonnegative_int(issue.get("signal_score"))
                + nonnegative_int(fit.get("score"))
                + DIFFICULTY_SCORE.get(difficulty, 0)
                + (10 if category == "Agent Skill" else 0)
                + scope_adjustment
            )
            candidates.append(
                {
                    "status": "needs_verification",
                    "repo": repository["repo"],
                    "issue": {
                        key: issue.get(key)
                        for key in ("number", "title", "url", "labels", "updated_at")
                    },
                    "selection_score": selection_score,
                    "why": [
                        *fit.get("reasons", []),
                        *issue.get("signal_reasons", []),
                        *scope_reasons,
                        *(
                            ["Agent Skill 仓库优先"]
                            if category == "Agent Skill"
                            else []
                        ),
                        f"仓库线索分 {repository.get('repository_signal_score', 0)}/40",
                    ],
                    "next_step": (
                        "先阅读完整 Issue、评论、贡献政策和相近 PR，再在当前默认分支"
                        "复现；查重与 RED 测试通过前不得开始修改。"
                    ),
                }
            )
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            -item["selection_score"],
            tuple(-part for part in time_rank(item["issue"].get("updated_at"))),
            item["repo"].lower(),
            item["issue"]["number"],
        )
    )
    return candidates[0]


def scan(
    seed: dict[str, Any],
    max_repos: int,
    max_issues: int,
    language: str | None,
    environment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if environment is None:
        environment = extend_environment_for_seed(detect_local_environment(), seed)
    items = seed["repositories"]
    if language:
        items = [
            item
            for item in items
            if str(item.get("language", "")).lower() == language.lower()
        ]
    items = sorted(items, key=lambda item: candidate_priority(item, environment))
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    skipped: list[dict[str, Any]] = []
    compatible_items: list[dict[str, Any]] = []
    for seed_item in items:
        local_fit = evaluate_local_fit(seed_item, environment)
        if local_fit["compatible"]:
            compatible_items.append(seed_item)
        else:
            skipped.append({"repo": seed_item["repo"], "local_fit": local_fit})
    for seed_item in compatible_items[:max_repos]:
        repo = seed_item["repo"]
        try:
            result = inspect_repository(repo, max_issues)
            if language and str(result.get("language") or "").lower() != language.lower():
                continue
            result["seed"] = {
                key: seed_item.get(key)
                for key in ("category", "difficulty", "reason", "stars_snapshot")
            }
            result["local_fit"] = evaluate_local_fit(seed_item, environment)
            result["best_issue_signal_score"] = max(
                (issue["signal_score"] for issue in result["issue_leads"]),
                default=0,
            )
            results.append(result)
        except Exception as exc:
            errors.append({"repo": repo, "error": redact(str(exc))})
    results.sort(
        key=lambda item: (
            -item["best_issue_signal_score"],
            -item["local_fit"]["score"],
            -item["repository_signal_score"],
            item["repo"].lower(),
        )
    )
    return {
        "schema_version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_snapshot_date": seed.get("snapshot_date"),
        "local_environment": environment,
        "warning": (
            "推荐项只是下一步深挖对象，不是可直接提交的 PR。提交代码前必须阅读"
            "贡献政策、检查重复项、在当前默认分支复现问题并运行项目原生测试。"
        ),
        "repositories": results,
        "recommended_opportunity": select_recommended_opportunity(results),
        "skipped_repositories": skipped,
        "errors": errors,
    }


def markdown_text(value: Any) -> str:
    return (
        redact(str(value or ""))
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# 开源贡献候选报告",
        "",
        f"生成时间：`{report['generated_at']}`",
        "",
        f"> {report['warning']}",
        "",
    ]
    environment = report.get("local_environment") or {}
    if environment:
        available = sorted(
            command for command, present in (environment.get("commands") or {}).items() if present
        )
        lines.extend(
            [
                "## 本机适配",
                "",
                f"- 平台：`{markdown_text(environment.get('platform'))}/"
                f"{markdown_text(environment.get('architecture'))}`",
                f"- 可用命令：{markdown_text(', '.join(available) or '未检测到')}",
                "",
            ]
        )
    recommendation = report.get("recommended_opportunity")
    lines.extend(["## 建议优先验证的 1 个机会", ""])
    if recommendation:
        issue = recommendation["issue"]
        lines.extend(
            [
                f"**{markdown_text(recommendation['repo'])} #{issue['number']}**："
                f"[{markdown_text(issue['title'])}]({markdown_text(issue['url'])})",
                "",
                f"- 选择分：{recommendation['selection_score']}（只用于排序）",
                f"- 原因：{markdown_text('；'.join(recommendation.get('why') or []))}",
                f"- 下一步：{markdown_text(recommendation['next_step'])}",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "本次没有找到同时满足本机依赖、许可证、未分配 Issue 和基础质量条件的机会。",
                "",
            ]
        )
    lines.extend(
        [
        "## 扫描结果",
        "",
        "| 仓库 | 语言 | Stars | 许可证 | 仓库线索分 | 最佳 Issue 线索分 |",
        "|---|---:|---:|---|---:|---:|",
        ]
    )
    for item in report["repositories"]:
        repo_name = markdown_text(item["repo"])
        repo_url = item.get("url") or f"https://github.com/{item['repo']}"
        lines.append(
            "| [{repo}]({url}) | {language} | {stars} | {license} | {repo_score}/40 | {issue_score}/60 |".format(
                repo=repo_name,
                url=markdown_text(repo_url),
                language=markdown_text(item.get("language") or "—"),
                stars=item.get("stars") or 0,
                license=markdown_text(item.get("license") or "待核实"),
                repo_score=item["repository_signal_score"],
                issue_score=item["best_issue_signal_score"],
            )
        )
    for item in report["repositories"]:
        lines.extend(["", f"## {markdown_text(item['repo'])}", ""])
        if not item["issue_leads"]:
            lines.append("暂无带目标标签的开放 Issue；不要据此推断仓库没有可贡献问题。")
            continue
        for issue in item["issue_leads"]:
            labels = markdown_text(", ".join(issue["labels"]) or "无标签")
            assigned = markdown_text(", ".join(issue["assignees"]) or "未分配")
            lines.append(
                f"- [#{issue['number']} {markdown_text(issue['title'])}]({markdown_text(issue['url'])}) "
                f"（线索分 {issue['signal_score']}/60；{labels}；{assigned}）"
            )
    if report["errors"]:
        lines.extend(["", "## 未能读取的仓库", ""])
        for error in report["errors"]:
            lines.append(
                f"- `{markdown_text(error['repo'])}`：{markdown_text(error['error'])}"
            )
    lines.append("")
    return "\n".join(lines)


def normalize_search_results(items: Any, repo: str) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        raise RadarError("搜索结果不是数组")
    expected_api_url = f"https://api.github.com/repos/{repo}".lower()
    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise RadarError("搜索结果包含非对象记录")
        repository = item.get("repository")
        name_with_owner = repository.get("nameWithOwner") if isinstance(repository, dict) else None
        repository_url = str(item.get("repository_url") or "").lower()
        if not name_with_owner and not repository_url:
            raise RadarError("搜索结果缺少仓库归属字段")
        if name_with_owner:
            belongs_to_repo = str(name_with_owner).lower() == repo.lower()
        else:
            belongs_to_repo = repository_url == expected_api_url
        if not belongs_to_repo:
            raise RadarError("搜索结果包含目标仓库之外的记录")
        number = nonnegative_int(item.get("number"))
        if number <= 0:
            raise RadarError("搜索结果包含无效编号")
        normalized.append(
            {
                "number": number,
                "title": str(item.get("title") or ""),
                "url": str(item.get("url") or item.get("html_url") or ""),
                "state": str(item.get("state") or "").lower(),
                "updated_at": item.get("updatedAt") or item.get("updated_at"),
                "repository": repo,
            }
        )
    return normalized


def search_duplicates(repo: str, terms: str, limit: int) -> dict[str, Any]:
    repo = validate_repo_name(repo)
    terms = validate_search_terms(terms)
    result: dict[str, Any] = {"repo": repo, "terms": terms, "errors": {}}
    searches = (
        ("open_issues", "issues", "issue", "open"),
        ("closed_issues", "issues", "issue", "closed"),
        ("open_prs", "prs", "pr", "open"),
        ("closed_prs", "prs", "pr", "closed"),
    )
    for key, gh_kind, api_kind, state in searches:
        query = f'"{terms}" repo:{repo}'
        try:
            data = gh_json(
                [
                    "search",
                    gh_kind,
                    query,
                    "--state",
                    state,
                    "--limit",
                    str(limit),
                    "--json",
                    "number,title,url,state,updatedAt,repository",
                ],
                timeout=60,
            )
            result[key] = normalize_search_results(data, repo)
        except RadarError as authenticated_error:
            public_query = urllib.parse.quote(
                f'repo:{repo} is:{api_kind} is:{state} "{terms}"'
            )
            try:
                public_result = public_api_json(
                    f"search/issues?q={public_query}&sort=updated&order=desc&per_page={limit}",
                    timeout=30,
                )
                if not isinstance(public_result, dict) or not isinstance(
                    public_result.get("items"), list
                ):
                    raise RadarError("公开搜索结果格式异常")
                result[key] = normalize_search_results(public_result["items"], repo)
            except RadarError as public_error:
                result[key] = []
                result["errors"][key] = redact(
                    f"认证搜索失败：{authenticated_error}；公开回退失败：{public_error}"
                )
    result["warning"] = (
        "标题搜索只是第一步；还需按错误文本、符号、文件名和根因再次搜索，"
        "并阅读相近 PR 的最终 diff。errors 中的项目代表未知，不能当作零结果。"
    )
    return result


def doctor() -> tuple[int, dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    required = ("git", "gh")
    for command in required:
        path = shutil.which(command)
        checks.append({"name": command, "ok": bool(path)})
    python_ok = sys.version_info >= (3, 9)
    checks.append(
        {
            "name": "python",
            "ok": python_ok,
            "version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        }
    )
    gh_ok = False
    user = None
    if shutil.which("gh"):
        try:
            run_command(["gh", "auth", "status"], timeout=20)
            account = gh_json(["api", "user", "--jq", "{login:.login}"], timeout=20)
            if isinstance(account, dict):
                user = account.get("login")
            gh_ok = bool(user)
        except RadarError as exc:
            checks.append({"name": "github_auth", "ok": False, "detail": redact(str(exc))})
        else:
            checks.append({"name": "github_auth", "ok": True, "login": user})
    else:
        checks.append({"name": "github_auth", "ok": False, "detail": "gh 未安装"})
    git_identity_ok = False
    if shutil.which("git"):
        try:
            name = run_command(["git", "config", "user.name"], timeout=10).strip()
            email = run_command(["git", "config", "user.email"], timeout=10).strip()
            git_identity_ok = bool(name and email)
            checks.append(
                {
                    "name": "git_identity",
                    "ok": git_identity_ok,
                    "configured": git_identity_ok,
                }
            )
        except RadarError as exc:
            checks.append({"name": "git_identity", "ok": False, "detail": redact(str(exc))})
    ok = all(
        item["ok"]
        for item in checks
        if item["name"] in {*required, "python", "github_auth", "git_identity"}
    )
    return (0 if ok and gh_ok and git_identity_ok else 1), {
        "ok": ok,
        "checks": checks,
        "local_environment": detect_local_environment(),
    }


def normalized_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def validate_output_paths(seed: Path, output: Path, markdown: Path, force: bool) -> None:
    paths = {"候选池": seed, "JSON 输出": output, "Markdown 输出": markdown}
    for label, path in paths.items():
        if path.is_symlink():
            raise RadarError(f"{label}不能是符号链接：{path}")
        if path.exists() and not path.is_file():
            raise RadarError(f"{label}必须是普通文件：{path}")
    normalized = {label: normalized_path(path) for label, path in paths.items()}
    if normalized["JSON 输出"] == normalized["Markdown 输出"]:
        raise RadarError("--output 与 --markdown 必须指向不同文件")
    if normalized["候选池"] in {normalized["JSON 输出"], normalized["Markdown 输出"]}:
        raise RadarError("输出文件不能覆盖候选池")
    existing_paths = list(paths.items())
    for index, (left_label, left_path) in enumerate(existing_paths):
        if not left_path.exists():
            continue
        for right_label, right_path in existing_paths[index + 1 :]:
            if right_path.exists() and os.path.samefile(left_path, right_path):
                raise RadarError(f"{left_label}与{right_label}不能指向同一文件")
    if not force:
        for label in ("JSON 输出", "Markdown 输出"):
            if normalized[label].exists():
                raise RadarError(f"{label}已存在：{normalized[label]}；覆盖请显式使用 --force")


def write_text_safely(path: Path, content: str, force: bool) -> None:
    expanded = path.expanduser()
    if expanded.is_symlink():
        raise RadarError(f"拒绝写入符号链接：{expanded}")
    target = expanded.absolute()
    target.parent.mkdir(parents=True, exist_ok=True)
    if not force:
        try:
            with target.open("x", encoding="utf-8", newline="") as handle:
                handle.write(content)
        except FileExistsError as exc:
            raise RadarError(f"输出文件已存在：{target}；覆盖请显式使用 --force") from exc
        return
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_name = handle.name
        # os.replace replaces a destination symlink entry itself; it never follows
        # the link to overwrite its target. The earlier check still rejects links
        # that existed when the operation began.
        os.replace(temporary_name, target)
        temporary_name = None
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)


def write_report_pair(
    output: Path,
    json_content: str,
    markdown: Path,
    markdown_content: str,
    force: bool,
) -> None:
    """Write both reports as one logical operation, rolling back partial writes."""
    targets = [output.expanduser().absolute(), markdown.expanduser().absolute()]
    contents = [json_content, markdown_content]
    if not force:
        created: list[Path] = []
        try:
            for target, content in zip(targets, contents):
                write_text_safely(target, content, force=False)
                created.append(target)
        except Exception:
            for target in created:
                target.unlink(missing_ok=True)
            raise
        return

    staged: dict[Path, Path] = {}
    backups: dict[Path, Path] = {}
    installed: list[Path] = []
    try:
        for target, content in zip(targets, contents):
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_symlink():
                raise RadarError(f"拒绝覆盖符号链接：{target}")
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                newline="",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".stage",
                delete=False,
            ) as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
                staged[target] = Path(handle.name)

        for target in targets:
            if target.exists():
                with tempfile.NamedTemporaryFile(
                    dir=target.parent,
                    prefix=f".{target.name}.",
                    suffix=".backup",
                    delete=False,
                ) as handle:
                    backup = Path(handle.name)
                backup.unlink()
                os.replace(target, backup)
                backups[target] = backup
            os.replace(staged[target], target)
            staged.pop(target, None)
            installed.append(target)
    except Exception:
        for target in installed:
            target.unlink(missing_ok=True)
        for target, backup in backups.items():
            if backup.exists():
                os.replace(backup, target)
        raise
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)
        for backup in backups.values():
            backup.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="开源贡献候选扫描器（GitHub 远端只读）")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="检查 git、gh、GitHub 登录与 Git 身份")

    scan_parser = subparsers.add_parser("scan", help="扫描候选池并生成 JSON/Markdown 报告")
    scan_parser.add_argument("--seed", type=Path, default=DEFAULT_SEED)
    scan_parser.add_argument("--max-repos", type=int, default=12)
    scan_parser.add_argument("--max-issues", type=int, default=5)
    scan_parser.add_argument("--language")
    scan_parser.add_argument("--output", type=Path, default=Path("contribution-report.json"))
    scan_parser.add_argument("--markdown", type=Path, default=Path("contribution-report.md"))
    scan_parser.add_argument("--force", action="store_true", help="原子覆盖已存在的本地报告")

    inspect_parser = subparsers.add_parser("inspect", help="查看一个仓库及其候选 Issue")
    inspect_parser.add_argument("repo")
    inspect_parser.add_argument("--max-issues", type=int, default=10)

    duplicate_parser = subparsers.add_parser("duplicates", help="搜索开放/关闭 Issue 与 PR 中的重复工作")
    duplicate_parser.add_argument("repo")
    duplicate_parser.add_argument("terms")
    duplicate_parser.add_argument("--limit", type=int, default=20)

    return parser


def bounded_int(value: int, name: str, minimum: int, maximum: int) -> int:
    if not minimum <= value <= maximum:
        raise RadarError(f"{name} 必须在 {minimum} 到 {maximum} 之间")
    return value


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "doctor":
            code, result = doctor()
            print(redact(json.dumps(result, ensure_ascii=False, indent=2)))
            return code
        if args.command == "scan":
            max_repos = bounded_int(args.max_repos, "--max-repos", 1, 50)
            max_issues = bounded_int(args.max_issues, "--max-issues", 1, 20)
            validate_output_paths(args.seed, args.output, args.markdown, args.force)
            seed = load_seed(args.seed)
            report = scan(seed, max_repos, max_issues, args.language)
            if not report["repositories"]:
                details = "; ".join(
                    f"{item['repo']}: {item['error']}" for item in report["errors"][:3]
                )
                raise RadarError(f"没有成功读取任何仓库，不生成报告。{details}")
            write_report_pair(
                args.output,
                redact(json.dumps(report, ensure_ascii=False, indent=2)) + "\n",
                args.markdown,
                markdown_report(report),
                args.force,
            )
            print(f"已写入 {args.output} 和 {args.markdown}")
            print(f"成功读取 {len(report['repositories'])} 个仓库，失败 {len(report['errors'])} 个")
            return 2 if report["errors"] else 0
        if args.command == "inspect":
            max_issues = bounded_int(args.max_issues, "--max-issues", 1, 50)
            print(
                redact(
                    json.dumps(
                        inspect_repository(args.repo, max_issues), ensure_ascii=False, indent=2
                    )
                )
            )
            return 0
        if args.command == "duplicates":
            limit = bounded_int(args.limit, "--limit", 1, 100)
            result = search_duplicates(args.repo, args.terms, limit)
            print(redact(json.dumps(result, ensure_ascii=False, indent=2)))
            return 2 if result["errors"] else 0
        raise RadarError(f"未知命令：{args.command}")
    except (OSError, RadarError) as exc:
        print(f"错误：{redact(str(exc))}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    configure_utf8_stdio()
    raise SystemExit(main())
