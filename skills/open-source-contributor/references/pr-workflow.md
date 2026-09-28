# PR 工作流参考

主 Skill 只保留原则和最常用命令。本页用于需要具体操作时按需加载；命令中的占位符应替换为当前仓库、分支和操作者自己的 GitHub 账号。

## 多仓库交付

本页由主 Agent 对每个通过独立验证的交付包分别执行。先进入该目标仓库的工作区，核对 remote、默认分支、补丁及受测 SHA；不要把不同子 Agent 的仓库或分支混用。每个 PR 解决一个独立问题，多个合格交付包可以形成多个 PR，不为增加数量拆分同一修复。

公开写入前确认授权覆盖该仓库、账号、操作和发布内容。优先使用宿主提供且适用于该目标的原生发布工具，遵守其仓库绑定和权限限制；下面的 CLI 命令是宿主允许使用时的参考，不用于绕过工具限制。只生成正文或命令不算交付，必须执行获授权的发布并回读上游 PR。

## 发布环境与认证预检

在主 Agent 派发实现任务前检查一次，实际发布前再核对。技能不要求开启 sandbox，也不要求 GitHub 操作在子 Agent 的隔离环境里完成；GitHub 是否接受请求取决于凭据、权限及网络条件，不能仅凭运行在 sandbox 中就断言认证不可用。

1. 主 Agent 选择宿主允许且支持目标仓库的原生 GitHub 工具或 CLI 发布环境，确认目标 GitHub host 和当前账号。CLI 路径可使用 `gh auth status --hostname HOST` 检查登录状态；不要使用显示 token 的选项或把认证输出原样写入公开报告。原生集成可能使用与 CLI 不同的账号，二者不能互相证明已登录。
2. 分别确认 GitHub API 的身份与仓库访问，以及 push 所用 HTTPS/SSH remote 和认证机制。API 登录成功不保证 Git push 可用；公开仓库读取成功也不证明有创建 fork、向 fork push 或向上游提 PR 的权限。不得通过创建测试 PR、推送测试分支来探测未授权的写权限。
3. 主 Agent 记录发布入口、目标账号/仓库和待满足的权限条件，不记录 token。认证可用不代表用户已授权公开写入；仍须按实际目标与内容确认授权。

### 隔离环境无法认证时

子 Agent 返回准确的错误类别和已完成的补丁/证据，由主 Agent 处理，不要求子 Agent 反复登录或自行找密钥。主 Agent 先判定：

- **隔离环境无法访问凭据或网络**：使用现有、已授权且可用的宿主发布集成；若必须变更执行权限，仅通过宿主明确提供的审批机制请求该次必要操作。宿主不提供或拒绝时，交给用户完成环境授权，不通过另起 CLI、关闭 sandbox 或复制凭据绕过限制。
- **登录失效或缺少登录**：请用户在宿主支持的登录流程中完成认证，再在相同发布环境复查。不要读取凭据文件、导出 token 或把宿主的 GitHub 密钥传给子 Agent。
- **仓库权限、组织 SSO 或网络错误**：根据实际错误请求对应授权或网络修复；401/403 不能一律归因于 sandbox，也不自动通过换仓库解决。

恢复认证后，从已保存的交付包继续发布，而不是重新做一次贡献。若发布工具不能直接访问子工作区，通过宿主允许的文件/补丁交接把已审查变更带到该目标仓库的发布工作区，核对基线、完整 diff 和受测版本；冲突、内容或基线变化后重新验证。仅做 Git 操作和远端回读，不把目标仓库的安装、测试、钩子或其他任意脚本自动提升到更高权限环境执行；这些操作仍遵守各自审批。

无法恢复时明确标为“补丁已验证，发布被认证/权限阻塞”，保存证据并请求具体解除条件，不声称 PR 已交付，也不把发布认证失败当成没有合格贡献机会。

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