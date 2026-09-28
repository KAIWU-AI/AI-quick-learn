---
name: 3d-video
description: Read a codebase and create a 16:9 Three.js/HyperFrames architecture video with continuous camera motion, labeled components, verified data flows and local assets. Includes optional Azure TTS via caller-owned environment credentials, reproducible preview/render commands, and no digital humans.
---

# 代码架构的连续3D视频

把**真实代码中的组件、边界和数据流**变成一个持续存在的三维场景，让镜头沿调用路径运动。不是把方框图逐页翻动，也不是给任意组件加旋转。默认静音，用户需要时可用自有Azure账号生成旁白；没有音乐和数字人。

## 先读与约束

1. 本技能目录叫`<SKILL>`；用户指定输出目录叫`<PROJECT>`。所有命令路径由实际安装位置解析，不依赖原作者目录。
2. 先读[架构理解流程](references/source-to-architecture.md)和[视觉/运镜要点](references/visual-language.md)。原工程有说明和图片时先用它们，再用代码确认；不把目标设计写成已实现。
3. 运行`node <SKILL>\scripts\project.mjs create --out <PROJECT> --example service`创建空的新工程。**不覆盖既有目录**；继续编辑时用`build`。
4. 架构以`architecture.json`为唯一数据入口：[数据格式](references/architecture-contract.md)。组件、位置、语义分组、关系、连续流和镜头都可替换；不在运行时硬编码业务名。
5. 场景适合3—12个关键组件；大项目按子系统分别生成，不把整个仓库所有类塞到一个画布里。代码语言不限；准确的架构归纳仍由阅读代码的Agent完成，工具不会凭空推断源码语义。

## 从源码到画面

- 定义一个问题，例如“一次订单如何被处理”。跟踪实际入口、验证、服务调用、状态保存、异步处理、结果回传。
- 为节点及关系指定`evidence`，指向` sources[].locator`的源文件/符号/文档位置。来源留在数据与工程说明，不在画面堆积路径。
- `implemented / planned / illustrative`必须准确。规划模块以虚线/“规划”标注，不参与当下已实现请求流。
- 数据包`request / event / result`用不同几何和颜色。`flows[].edges`是一条连续路径：相邻边必须共享端点；一个数据包全程保持对象身份，不能在门禁前消失再换一个。
- 文字默认为组件名称+功能短注，不放技术菜单、页码和重复口号。中文和英文由用户内容选择，不强制双语。
- 镜头从整体→核心节点→处理结果→整体，至少一次有理由的角度变化；不要逐页重建组件、晃动所有标签。

## 构建、预览、验证

预览只需Node.js，无需安装依赖。Three.js、GSAP、字体、模型、木纹、HDRI均已冻结在包中，运行画面不访问CDN。

```powershell
node <SKILL>\scripts\project.mjs create --out <PROJECT> --example service
# 编辑 <PROJECT>\architecture.json
node <SKILL>\scripts\project.mjs build --project <PROJECT>
node <SKILL>\scripts\project.mjs preview --project <PROJECT> --port 4020
```

预览服务在前台运行；终端须保持打开。打印的地址包含`/review/`，只绑定`127.0.0.1`。端口占用时报错，不结束别人的进程，不自动隐藏或分离后台。

渲染首次需要联网安装锁定的CLI/测试依赖；Node.js22+、FFmpeg/FFprobe和Chromium环境不装进ZIP：

```powershell
Set-Location <SKILL>
npm ci
npm test
node scripts\project.mjs check --project <PROJECT>
node scripts\inspect.mjs --project <PROJECT>
# 用户确认预览后才导出
node scripts\project.mjs render --project <PROJECT> --approved
```

`inspect`需要`CHROME_PATH`指定Chrome/Edge/Chromium可执行文件；支持Windows/macOS/Linux的常见路径查找。它只控制自己启动的浏览器。`render`使用安装在**此技能包**内的HyperFrames0.8.4，`high`画质，默认2个worker，无音轨。不会从另一个项目借CLI、默默升级或上传源码。

## 必须通过的门禁

- `build`：严格字段、ID、端点、证据引用、规划边界、相邻路径与时长校验。无效输入报错，不生成看似成功的空场景。
- `check`：HyperFrames真实运行时、布局、运动、对比度。Canvas内部运动由`inspect`补充。
- `inspect`：组件持久身份；相同时间正向/逆向寻帧；连续路径；标签/安全区；真实截图；零远端网络请求；默认无音轨，无数字人或业务视频。
- 配音模式允许经过校验的`audio`元素，仍禁止数字人/业务素材视频。`inspect`记录音轨数量；render核对最终音轨是否存在。
- `render`：完整解码、尺寸/帧率/时长、无音轨；关键帧与整段画面需人工审看。输出体积非零不能替代质量检查。
- 修改运行源码后重新build/check/render；旧截图和旧MP4不能继续作为新版本验证。
- 资产与授权见[ASSETS.md](ASSETS.md)和[LICENSES.md](LICENSES.md)。禁止带入凭据、人物素材、参考人声、品牌商店标识或用户业务视频。

## 交付

交付项目目录、`renders/architecture.mp4`、`architecture.json`、来源说明及`qa/`。若用户要技能包ZIP，运行`node scripts/package.mjs zip --out <ZIP>`；该命令按白名单打包并校验哈希，排除依赖树、工作工程和缓存。不加入数字人。

## 可选Azure旁白

先读[Azure TTS接入](references/azure-tts.md)。按镜头写`narration.json`；运行`node scripts/tts.mjs --project <PROJECT> --prepare`得到可审阅SSML。只有用户明确同意将这份讲解稿发往自己的Azure资源后，使用进程环境中的`AZURE_SPEECH_KEY`和`AZURE_SPEECH_REGION`执行`--approved`。不提供密钥、不自动查找本机秘密、不调用登录命令。自动记录词边界、音频哈希和实测时长；超时长报错，不静默换声或加速。音色和读音仍须试听。

完整命令与常见问题见[构建与依赖](references/build-and-verify.md)。两个不同业务示例在`examples/service.json`、`examples/pipeline.json`，均是明确标注的教学示例，不是任何真实线上系统。
