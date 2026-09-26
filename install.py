#!/usr/bin/env python3
"""把 open-source-pr-contributor 技能安装到常见 Coding Agent 目录。"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SOURCE = REPO_ROOT / "skills" / "open-source-pr-contributor"
DEFAULT_ROOTS = {
    "hermes": Path.home() / ".hermes" / "skills",
    "claude": Path.home() / ".claude" / "skills",
    "codex": Path.home() / ".agents" / "skills",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="安装高质量开源贡献技能")
    parser.add_argument("--agent", choices=[*DEFAULT_ROOTS, "custom"], default="hermes")
    parser.add_argument("--target", type=Path, help="自定义 skills 根目录；--agent custom 时必填")
    parser.add_argument("--force", action="store_true", help="更新已安装技能；旧版本先备份")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def validate_skill_tree(root: Path) -> None:
    skill_file = root / "SKILL.md"
    script_file = root / "scripts" / "contribution_radar.py"
    pool_file = root / "references" / "repository-pool.json"
    if not skill_file.is_file() or not script_file.is_file() or not pool_file.is_file():
        raise RuntimeError("技能目录不完整：缺少 SKILL.md、扫描脚本或候选池")
    try:
        content = skill_file.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise RuntimeError("SKILL.md 无法读取") from exc
    if not content.startswith("---\n") or "name: open-source-pr-contributor" not in content:
        raise RuntimeError("SKILL.md frontmatter 无效")
    try:
        pool = json.loads(pool_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("候选池 JSON 无效或不可读") from exc
    repositories = pool.get("repositories") if isinstance(pool, dict) else None
    if not isinstance(repositories, list) or not repositories:
        raise RuntimeError("候选池必须包含非空 repositories 数组")
    names: list[str] = []
    for item in repositories:
        if not isinstance(item, dict) or not isinstance(item.get("repo"), str):
            raise RuntimeError("候选池条目必须包含字符串 repo")
        name = item["repo"]
        if name.count("/") != 1 or any(part in {"", ".", ".."} for part in name.split("/")):
            raise RuntimeError(f"候选池仓库名无效：{name!r}")
        if item.get("difficulty") not in {"low", "medium", "high"}:
            raise RuntimeError(f"候选池 difficulty 无效：{name!r}")
        setup = item.get("setup")
        if not isinstance(setup, dict) or setup.get("level") not in {
            "light",
            "moderate",
            "heavy",
        }:
            raise RuntimeError(f"候选池 setup.level 无效：{name!r}")
        required_commands = setup.get("required_commands")
        platforms = setup.get("platforms")
        if not isinstance(required_commands, list) or not all(
            isinstance(command, str) and command for command in required_commands
        ):
            raise RuntimeError(f"候选池 required_commands 无效：{name!r}")
        if not isinstance(platforms, list) or not platforms:
            raise RuntimeError(f"候选池 platforms 无效：{name!r}")
        names.append(name.lower())
    if len(names) != len(set(names)):
        raise RuntimeError("候选池包含重复仓库")


def validate_source() -> None:
    validate_skill_tree(SOURCE)


def resolve_destination(args: argparse.Namespace) -> Path:
    if args.agent == "custom":
        if args.target is None:
            raise RuntimeError("--agent custom 必须同时提供 --target")
        root = args.target.expanduser()
    elif args.target is not None:
        root = args.target.expanduser()
    else:
        root = DEFAULT_ROOTS[args.agent]
    destination = root.absolute() / "open-source-pr-contributor"
    source_real = SOURCE.resolve()
    destination_real = destination.resolve(strict=False)
    if destination_real == source_real or source_real in destination_real.parents:
        raise RuntimeError("安装目标不能是源码目录或其子目录")
    return destination


def install(destination: Path, force: bool, dry_run: bool) -> Path | None:
    backup = None
    if destination.is_symlink():
        raise RuntimeError(f"拒绝安装到符号链接：{destination}")
    if destination.exists():
        if not force:
            raise RuntimeError(f"目标已存在：{destination}；更新请加 --force")
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = destination.with_name(f"{destination.name}.backup-{stamp}")
        if backup.exists():
            raise RuntimeError(f"备份目标已存在：{backup}")
    if dry_run:
        return backup
    destination.parent.mkdir(parents=True, exist_ok=True)
    if backup:
        destination.rename(backup)
    try:
        shutil.copytree(
            SOURCE,
            destination,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        validate_skill_tree(destination)
    except Exception:
        if destination.exists():
            shutil.rmtree(destination)
        if backup and backup.exists():
            backup.rename(destination)
        raise
    return backup


def main() -> int:
    args = parse_args()
    try:
        validate_source()
        destination = resolve_destination(args)
        backup = install(destination, args.force, args.dry_run)
    except (OSError, RuntimeError) as exc:
        print(f"安装失败：{exc}", file=sys.stderr)
        return 2
    action = "将安装" if args.dry_run else "已安装"
    print(f"{action}：{SOURCE} -> {destination}")
    if backup:
        print(f"旧版本备份：{backup}")
    if not args.dry_run:
        print("请重启或新建 Coding Agent 会话，使技能索引重新加载。")
        command = [sys.executable, str(destination / "scripts" / "contribution_radar.py"), "doctor"]
        rendered = subprocess.list2cmdline(command) if os.name == "nt" else shlex.join(command)
        print(f"验证命令：{rendered}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
