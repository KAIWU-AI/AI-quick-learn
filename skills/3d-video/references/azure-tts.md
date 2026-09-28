# 可选 Azure TTS：只带能力，不带密钥

本技能不读取原工程的Azure配置、不调用Azure CLI、不扫描OneDrive/用户目录、不提供自己的服务端代理。默认视频静音。用户显式需要讲解时，**只将审核后的旁白文字发送给Azure Speech**；源码、架构证据、模型、图片不上传。

## 1. 准备稿件

把`examples/narration.json`复制到生成工程的`narration.json`，根据真实架构修改。每行只有`start`、`end`、`text`，分别为成片绝对时间窗口和要读的文本。例子给24秒service场景，不能照搬到其他时长。

```powershell
node scripts/tts.mjs --project work/demo --prepare
```

只写可审查的`narration-plan/*.ssml`，不需要密钥、不会发送请求。正文以纯文本XML转义；不可把任意XML/外部实体当输入。

## 2. 环境变量（值由使用者自行填写）

在自己的终端/密钥管理器中设置`AZURE_SPEECH_KEY`和`AZURE_SPEECH_REGION`。PowerShell用`$env:变量名`，macOS/Linux用`export`。**不要把真实值写进聊天、脚本、JSON、仓库或ZIP，也不要将含密钥终端命令录屏。** Region例如`eastus`，不是key或endpoint。

```powershell
# 两个变量已由你在当前进程中安全配置后：
node scripts/tts.mjs --project work/demo --approved
```

默认女声`zh-CN-Xiaoxiao2:DragonHDFlashLatestNeural`，语速0%、音调0Hz。完整voice ID可通过`--voice`覆盖。服务不可用时报错，绝不静默换声或批量试所有声音。按量消耗自己的Azure额度；串行合成、无自动收费重试。

## 3. 实测与接入

输出MP3为24kHz/48kbps/mono。记录SDK词边界、实测FFprobe时长、完整解码与内容哈希。`narration-manifest.json`经校验后由build生成原生HyperFrames音轨，preview有声，render可导出有声MP4。

缓存按SSML、声音和参数哈希命名。改变文本/声线后不会复用旧音轨。已生成音频超出窗口时停止，保留原文件供判断；需缩短稿子或调整镜头，不自动加速、截字或把失败变成静音。

每个词边界使用秒，来自100ns事件值换算；这是服务返回的对齐数据，不是独立音素准确性证据。拼音、术语、专名需实际试听。无密钥交付环境只验证准备流程、缓存与模拟SDK测试，不能声称已完成真实Azure云合成。

## 安装

在技能包根目录`npm ci`安装锁定SDK1.48.0。ZIP不包含node_modules、任何真实`.env`、token或已有语音；不加入数字人功能。
