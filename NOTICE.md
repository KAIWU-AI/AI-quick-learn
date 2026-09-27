# 来源与改编说明

`open-source-pr-contributor` 基于当前工作环境中使用的以下 MIT 许可 Hermes Agent 技能进行中文、通用化改编：

- `open-source-repo-portfolio` v1.3.4，SHA-256：`912af8331758869e3620799638908c017d6e7dddf394f99f6eff1cf3ad360673`
- `trending-open-source-contributor` v1.5.0，SHA-256：`cf18150e43ce42908a49f4f888c661ca29d19f2833f005a852c2c28feae7b106`

原始技能作者标记为 Hermes Agent。

## 保留的核心方法

- 长期候选仓库池与动态机会发现并行；
- 先核验许可证、维护活跃度、外部 PR 接受情况和本地测试可行性；
- 在修改前检查贡献政策、Issue 所有权和重复工作；
- 使用同一测试完成 RED → GREEN 证明；
- 最小修复、独立审查、远端回读和 CI 跟进；
- 没有高质量候选时允许不提交 PR。

## 删除或泛化的内容

- 本机绝对路径、用户名、账号和私有工作区状态；
- 特定 Cron、日报、仪表盘和内部账本流程；
- 仅适用于单一组织或单一仓库的权限规则；
- 与个人运行环境绑定的恢复、投递和维护逻辑。

## 新增内容

- 中文工作流；
- 面向 Hermes Agent、Claude Code、Codex 和自定义目录的安装器；
- 无第三方 Python 依赖的 GitHub 候选扫描与查重脚本；
- 22 个跨领域公开仓库的可扩展种子池；
- 安装、输入校验、凭据清理、文件写入和候选池测试；
- Linux、macOS、Windows 的持续集成验证。

本仓库整体采用 MIT License，详见 `LICENSE`。
