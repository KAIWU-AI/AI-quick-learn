# Demo 1：看懂两个 API 的输入和返回

**本课只学习直接 API 调用，不加对话记忆、工具或 Agent Loop。** 默认对同一段虚构客服工单分别发出两个独立请求：

| API | 发送什么 | 返回什么 |
|---|---|---|
| 大语言模型 · OpenAI Responses | `instructions` + `input` | 自然语言分类和解释，以及 `output`、`usage` 等结构 |
| JEV · TypeSafe systemone | `state` + `questions` + `criteria` | 类型化 `choice`、`confidence` 和各选项 `probabilities` |

两次调用由普通 Python 顺序执行，不是模型选择工具，也不是自动循环。

## 运行

先按[根目录 README](../README.md#三个-ai-基础-demo)安装依赖，将根目录 `.env.example` 复制为 `.env` 并填入配置。真实密钥只放在 Git 忽略的 `.env` 或系统凭据管理器，不能放进可分享的 `.env.example`。

跨平台 JEV 配置：

```dotenv
JEV_AUTH=api-key
JEV_API_KEY=YOUR_JEV_API_KEY
JEV_MODEL=jev-latest
```

如果当前 Windows 用户已经保存了 JEV 凭据，可以不写明文密钥：

```dotenv
JEV_AUTH=windows-credential
JEV_CREDENTIAL_TARGET=TypeSafe/Jev/APIKey
JEV_MODEL=jev-latest
```

这个模式只读取现有凭据，不创建或覆盖它；其他平台使用环境变量或本地 `.env`。大语言模型仍使用 `OPENAI_*` 配置，JEV Key **不是** `OPENAI_API_KEY`，其接口也不是 Responses 兼容地址。

激活虚拟环境后，在仓库根目录执行：

```bash
python -m demo1
python -m demo1 "软件打开后一直闪退，重装也没有解决。"
```

默认生成 `demo1/result.html`，直接用浏览器打开。可用 `--output 路径.html` 改变输出位置；重复运行会更新该文件。报告默认被 Git 忽略。

只观察 JEV 请求代码或单独测试它：

```bash
python -m demo1.jev "我被重复扣款了，请帮我退款。"
```

## 如何阅读可视化

先看共享工单，再并排看两个 API 的结果摘要和用量；随后沿请求树、返回树逐层展开：

- **对象和数组**：看 key、索引、类型、子项数量及嵌套关系，不需要盯着大段 JSON 字符串。
- **大语言模型**：在 `output[]` 中展开 `type: message` 的项目，再在 `content[]` 中找到 `type: output_text` 的项目，读取其 `text`。SDK 的 `response.output_text` 是提取文字的便捷属性，不等于完整返回。
- **JEV**：`state.document` 是证据；`questions.category` 定义判断；`criteria` 给出可选分类；`answers.category.choice` 是选中的分类。
- **概率条形图**：`probabilities` 对比竞争选项。`confidence` 表示分布集中程度，**不是事实正确率**；大语言模型没有返回同义数值时不补造一个。
- **用量与耗时**：未报告的字段标记为未提供。耗时包含本地认证、网络等开销，是单次观测，不能据此宣布哪一个服务普遍更快、更准或更便宜。

界面旁的字段注释是教学解读，不是模型额外生成的推理。嵌套 JSON 保留供检查，加密 reasoning 状态在终端和页面中均遮蔽，不修改内存中的原始响应；所有输入和返回都按文本转义，不作为 HTML 执行。

若一边失败，仍会显示另一边的真实结果，并在失败卡片上显示错误；程序以非零状态退出，不把部分成功包装成全部成功。不把鉴权头、API Key 或 Windows 凭据内容写进页面。

## 动手改一处

把“重复扣款”换成“软件闪退”，再换成“我想修改收货地址”，观察两种接口分别如何表达判断。再试一个信息不足的工单，检查 JEV 的选项分布；单个样例不是校准或准确率评估。

下一课暂时只使用大语言模型，增加历史列表，理解多轮对话记忆。
