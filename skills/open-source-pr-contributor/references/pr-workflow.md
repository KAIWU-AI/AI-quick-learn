# PR 工作流参考

主 Skill 只保留原则和最常用命令。本页用于需要具体操作时按需加载；命令中的占位符应替换为当前仓库、分支和操作者自己的 GitHub 账号。

## 建立工作分支

从最新上游默认分支创建一个聚焦分支。先确认工作树、remote 和默认分支，避免覆盖已有工作。

```bash
git fetch upstream
git switch -c fix/short-description upstream/main
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
gh pr create \
  --repo OWNER/REPO \
  --base DEFAULT_BRANCH \
  --head USER:BRANCH \
  --title "fix(scope): concise outcome" \
  --body-file pr-body.md
```

只有真正完整解决对应 Issue 时才使用 `Fixes #ISSUE`。

## 回读与跟进

```bash
gh pr view PR_URL --json url,state,headRefOid,files,statusCheckRollup
gh pr checks PR_URL
```

确认远端 head 与本地提交一致，区分补丁失败和上游基础设施问题。收到 review 后读取完整上下文，修复有效意见，并继续跟进到合并、关闭或明确阻塞。