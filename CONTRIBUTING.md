# 贡献指南

欢迎改进候选池、扫描器和中文 Skill。请让每次修改保持小而可验证。

## 提交前

1. 创建或关联一个说明问题、预期行为和验收标准的 Issue。
2. 检查开放与关闭 PR，避免重复工作。
3. 不提交 Token、Cookie、`.env`、私有路径、扫描报告或用户数据。
4. 新增行为必须补充测试；修复必须能说明修改前后的差异。

## 本地验证

```bash
python3 -m unittest discover -s skills/open-source-pr-contributor/tests -v
python3 -m unittest discover -s tests -v
python3 skills/open-source-pr-contributor/scripts/contribution_radar.py doctor
```

涉及在线扫描时，可用少量公开仓库做验证：

```bash
python3 skills/open-source-pr-contributor/scripts/contribution_radar.py scan --max-repos 2 --max-issues 2
```

## PR 内容

PR 请说明：

- 当前问题与用户影响；
- 最小修改范围；
- 实际运行的测试及结果；
- 是否改变脚本的公开操作边界；
- 是否更新候选池快照日期。

如果使用 AI 辅助，请确保提交者理解并审查全部改动，对结果负责。
