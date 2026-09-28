# Code Architecture 3D

可迁移的**3D架构视频技能包，支持可选Azure讲解配音**。从原有连续架构演示中提炼运镜、流动路径、实体材质、柔和标签、木质底座与可寻帧构建方式，去除原业务、声音样本、人物、云账号及本机路径。ZIP不带任何密钥。

先读[SKILL.md](SKILL.md)，然后：

```powershell
# 在解压后的技能根目录执行
node scripts/project.mjs create --out work/demo --example service
node scripts/project.mjs preview --project work/demo --port 4020
```

浏览器打开打印出的地址；保持终端运行。修改生成工程里的`architecture.json`后，执行`node scripts/project.mjs build --project work/demo`并刷新。

导出：

```powershell
npm ci
npm test
node scripts/project.mjs check --project work/demo
node scripts/inspect.mjs --project work/demo
node scripts/project.mjs render --project work/demo --approved
```

Linux/macOS使用同样的Node命令；Windows文档可使用反斜杠。**ZIP带渲染资源，不带Node、Chrome、FFmpeg、node_modules**。首次`npm ci`及HyperFrames浏览器准备可能需要网络；离线预览不需要网络或模型账号。桌面平台支持范围以验证记录为准，不把Windows实测冒充三平台已实测。

## 包中包含

- `SKILL.md`：Agent可加载的技能入口；标准文件名大小写，避免在Windows同时放skill.md与SKILL.md。
- `references/`：架构理解、表达原则、数据合同、构建与排错。
- `runtime/`：通用场景、组件、标签、静音星空、预览播放器。
- `scripts/`：create/build/preview/check/render/inspect/zip。
- `examples/`：同步服务链与异步流水线两套不同拓扑，含来源说明。
- `assets/`：本地Three.js/GSAP、开源中文字体、Kenney工作站模型、木纹与摄影棚HDRI、许可证。
- `tests/`：输入验证、路径连续性、包隔离、安全路径测试。
- `scripts/tts.mjs`：可审阅SSML、调用者环境凭据、逐段Azure合成、词边界、实测时长和缓存；[接入说明](references/azure-tts.md)。
- 源码包不附历史渲染证据；生成工程中的验证记录和画面需要在使用者环境中实际产生，不能将单元测试通过当作渲染通过。

本技能自有代码采用仓库的 MIT License，完整原文及适用边界见 [LICENSES.md](LICENSES.md)，该文件随独立 ZIP 和 create 生成工程一并提供。第三方资源分别遵循 `assets/licenses/` 中的原始许可：Three.js 为 MIT、Noto 字体为 OFL-1.1、Kenney 与 Poly Haven 资源为 CC0；GSAP 为 GSAP Standard License（不是 MIT，须遵守其用途限制）。不得将整包第三方资源统一标记为 MIT。

**适用任意代码架构的表达，不等于一键理解任意源码。**阅读源代码、确定边界和选择关键节点是技能执行步骤；渲染器接收结构化JSON，不执行被分析项目，不上传代码。

Azure配音仅上传用户批准的旁白文字，消耗使用者自己的Azure额度。无密钥仍可预览/导出静音版，或准备SSML；不会偷偷采用其他账号或声音服务。
