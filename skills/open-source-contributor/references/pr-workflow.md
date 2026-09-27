# PR 工作流参考

主 Skill 只保留原则和最常用命令。本页用于需要具体操作时按需加载；命令中的占位符应替换为当前仓库、分支和操作者自己的 GitHub 账号。

## 多仓库交付

本页由主 Agent 对每个通过独立验证的交付包分别执行。先进入该目标仓库的工作区，核对 remote、默认分支、补丁及受测 SHA；不要把不同子 Agent 的仓库或分支混用。每个 PR 解决一个独立问题，多个合格交付包可以形成多个 PR，不为增加数量拆分同一修复。

公开写入前确认授权覆盖该仓库、账号、操作和发布内容。优先使用宿主提供且适用于该目标的原生发布工具，遵守其仓库绑定和权限限制；下面的 CLI 命令是宿主允许使用时的参考，不用于绕过工具限制。只生成正文或命令不算交付，必须执行获授权的发布并回读上游 PR。

## 建立工作分支

从最新上游默认分支创建一个聚焦分支。先确认工作树、remote 和默认分支，避免覆盖已有工作。

```bash
git fetch upstream
git switch -c fix/short-description upstream/DEFAULT_BRANCH
```

## 检查修改

提交前确认 diff 只包含本次贡献，并运行项目要求的测试和检查。

```bash
git status --short
git diff --check
git diff --stat
git diff
```

## Fork、提交与推送

```bash
gh repo fork OWNER/REPO --clone=false
git remote add origin https://github.com/USER/REPO.git
git add <changed-files>
git commit -m "fix(scope): describe the outcome"
git push -u origin HEAD
```

如果 remote 已存在，先核对其目标，不要直接覆盖。项目要求 DCO、签名或其他提交格式时，以项目规则为准。

## 创建 PR

优先使用项目自己的 PR 模板。正文只写问题、影响、改动和实际测试结果。

```bash
gh pr create --repo OWNER/REPO --base DEFAULT_BRANCH --head USER:BRANCH --title "fix(scope): concise outcome" --body-file pr-body.md
```

只有真正完整解决对应 Issue 时才使用 `Fixes #ISSUE`。

## 回读与跟进

```bash
gh pr view PR_URL --json url,state,headRefOid,files,statusCheckRollup
gh pr checks PR_URL
```

确认远端 head 与本地提交一致，区分补丁失败和上游基础设施问题。收到 review 后读取完整上下文，修复有效意见，并继续跟进到合并、关闭或明确阻塞。

创建请求超时或响应不明时，先按仓库和 head 分支查询远端是否已存在 PR，避免重复创建。逐个记录 PR URL、目标仓库、关联问题、head SHA、变更文件、测试和 CI 状态；待运行或失败的 CI 不能标为通过。一个仓库受阻时不阻塞其他已验证且获授权的交付包。最终没有真实上游 PR 时，报告未完成和具体阻塞，不用草稿或本地补丁冒充交付。