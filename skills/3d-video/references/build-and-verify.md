# 可复现构建方式

## 核心依赖

| 环节 | 要求 |
|---|---|
| 创建、构建、预览、打包 | Node.js22+；仅标准库 |
| 画面运行 | 随包Three.js r185、GSAP3.14.2、Noto Sans SC、模型和材质 |
| 自动检查、MP4渲染 | `npm ci`：HyperFrames0.8.4、puppeteer-core25.6.0、pngjs7.0.0 |
| 可选旁白 | 同次安装的Microsoft Speech SDK1.48.0；用户提供环境变量，默认不调用 |
| 浏览器 | Chrome/Edge/Chromium；`inspect`可用`CHROME_PATH`；HyperFrames可准备自己的缓存浏览器 |
| 媒体检查与编码 | FFmpeg、FFprobe在PATH；不打包这些二进制 |

不要从其他项目的node_modules借版本，不查找私有主目录。npm锁文件是工具依赖唯一来源。安装依赖和首次获取浏览器可以联网；预览/渲染资源不热链到CDN，源代码也不发送到外部服务。

## 操作

```powershell
node scripts/project.mjs create --out work/demo --example service
node scripts/project.mjs create --out work/pipeline --example pipeline
node scripts/project.mjs build --project work/demo
node scripts/project.mjs preview --project work/demo --port 4020
```

另开终端安装与检查：

```powershell
npm ci
npm test
node scripts/project.mjs check --project work/demo
node scripts/inspect.mjs --project work/demo
node scripts/project.mjs render --project work/demo --approved
```

自定义输入：`create --example <architecture.json路径> --out <新工程>`；复制后在生成工程内编辑。build只更新index、review和构建摘要，不重新覆盖自定义的runtime/assets。

导出文件存在时拒绝覆盖。可用`--out work/demo/renders/architecture-v2.mp4`选择新文件。worker默认2，支持1—4；共享机器或显存不足时用`--workers 1`，不要结束其他应用。

## 排错

- **文件双击无法加载模型**：使用Node预览服务器，不用`file://`运行ESModules。
- **端口占用**：换`--port`；不自动杀占用进程。
- **缺少HyperFrames/SDK**：在技能根目录`npm ci`，不是生成工程里装不一致版本。
- **字体空白**：确认随包字体哈希、等待`document.fonts.ready`；不要用占位方块当成功。
- **节点挤在一起**：修改位置/镜头distance、缩短标签；大架构拆分，而不是降低字号。
- **流突然换对象/消失**：检查flows的相邻edge端点；一个flow只绑定一个持久mesh。
- **画面经审看仍不好**：技术检查不能证明美观，保留前中后及实际编码帧作比较。
- **Windows CLI异常退出**：不以文件存在作成功；保留日志，独立完整解码/帧数/画面/音频检查。修复后新文件重渲染，不静默吞退出码。
- **Azure音频超窗**：保留缓存，编辑稿子或end/duration及镜头；不隐藏问题、不自动变速。

## 包本身

```powershell
node scripts/schema.mjs > architecture.schema.json
node scripts/package.mjs seal
node scripts/package.mjs verify
node scripts/package.mjs zip --out dist/3d-video.zip
```

seal在全部工作确认后运行，更新逐文件哈希。ZIP仅包含明确白名单；运行原始包、解压后的包各一次，生成工程必须位于新路径，不能偷偷访问原工程。

## 审查重点

按0、1/4、中间、3/4、最后帧审查组件、关系、planned状态、标签可读与连续运镜。默认导出无音轨；配音版只能引用本工程的已验证音频manifest。评估实际MP4，而不只看预览或lint。
