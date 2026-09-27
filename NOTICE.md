# 来源与改编说明

`open-source-contributor` 基于以下 MIT 许可 Hermes Agent 技能进行中文、通用化改编：

- `open-source-repo-portfolio` v1.3.4，SHA-256：`912af8331758869e3620799638908c017d6e7dddf394f99f6eff1cf3ad360673`
- `trending-open-source-contributor` v1.5.0，SHA-256：`cf18150e43ce42908a49f4f888c661ca29d19f2833f005a852c2c28feae7b106`

原始技能作者标记为 Hermes Agent。

## 保留的核心方法

- 长期候选仓库池与动态机会发现并行；
- 先核验许可证、维护活跃度、外部 PR 接受情况和本地测试可行性；
- 在修改前检查贡献政策、Issue 所有权和重复工作；
- 使用同一测试完成 RED → GREEN 证明；
- 最小修复、独立审查、远端回读和 CI 跟进；
- 不以低质量 PR 冒充完成；教学任务没有提交真实 PR 时应明确标记未完成。

## 删除或泛化的内容

- 本机绝对路径、用户名、账号和私有工作区状态；
- 特定 Cron、日报、仪表盘和内部账本流程；
- 仅适用于单一组织或单一仓库的权限规则；
- 与个人运行环境绑定的恢复、投递和维护逻辑。

## 新增内容

- 中文工作流；
- 面向 Hermes Agent、Claude Code、Codex 和自定义目录的安装器；
- 无第三方 Python 依赖的 GitHub 候选扫描与查重脚本；
- 30 个公开仓库的可扩展种子池，保留 Agent Skill 项目并补充轻量 Python 库；
- 可复现的随机分流、已查仓库排除与多轮发现；
- 与通用流程分离、按需加载的课程贡献兜底引用；
- 安装、输入校验、凭据清理、文件写入和候选池测试；
- Linux、macOS、Windows 的持续集成验证。

本仓库整体采用 MIT License，详见 `LICENSE`。

## AI 基础 Demo 的教学参考

`demo1`、`demo2`、`demo3` 借鉴了 [shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) 每课引入一个机制、保留可读主循环、用运行轨迹验证理解的教学方式。参考版本为 `0dcafa2ae053a1ddd6a72f265431104b08a5aa13`，重点包括 `agents/s01_agent_loop.py` 的循环与工具反馈机制。

上游采用 [MIT License](https://github.com/shareAI-lab/learn-claude-code/blob/0dcafa2ae053a1ddd6a72f265431104b08a5aa13/LICENSE)，署名为 Copyright (c) 2024 shareAI Lab。本项目的代码与中文讲解为独立实现，不是上游代码或章节的逐行翻译；三个 Demo 按“直接调用 → 对话记忆 → 多工具 Agent Loop”重新编排。

协议与认证写法参考 [OpenAI Responses API](https://platform.openai.com/docs/api-reference/responses)、[OpenAI function calling](https://platform.openai.com/docs/guides/function-calling) 和 [Azure OpenAI Responses API](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/responses)。
