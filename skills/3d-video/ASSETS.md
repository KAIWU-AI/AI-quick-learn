# Curated asset inventory

原始模型/纹理/运行时按白名单复制；来源不等于重新授权，第三方原始许可证见`assets/licenses/`。逐文件SHA-256见`assets/manifest.json`与`bundle-manifest.json`。

| Payload | Fixed source | License / use |
|---|---|---|
| `vendor/three.*.min.js`, GLTF/HDR loaders and utilities | Three.js r185, commit `2431a09f46f34c560bc8e44b33be0e567723d5b9` | MIT; matching versions, no CDN |
| `vendor/gsap.min.js` | npm `gsap@3.14.2` | GSAP Standard License; license text preserved |
| `fonts/NotoSansSC.ttf` | google/fonts commit `a85815a42757630ce188fdad368c2dfc444d4773`, `ofl/notosanssc/NotoSansSC[wght].ttf` | SIL OFL1.1; full Chinese font, no system-font dependency |
| `models/computerScreen.glb`, keyboard/mouse | Kenney Furniture Kit2.0, 2018-10-20 package | CC0; original glTFs unchanged |
| `textures/walnut/*.jpg` | Poly Haven `natural_walnut_veneer`, Jenelle van Heerden | CC0; color/roughness/OpenGL normal1K |
| `hdri/studio.hdr` | Poly Haven `studio_small_09`, Sergej Majboroda | CC0;1K studio lighting |

Creator pages:

- https://github.com/mrdoob/three.js/tree/2431a09f46f34c560bc8e44b33be0e567723d5b9
- https://registry.npmjs.org/gsap/3.14.2
- https://gsap.com/standard-license/
- https://github.com/google/fonts/tree/a85815a42757630ce188fdad368c2dfc444d4773/ofl/notosanssc
- https://kenney.nl/assets/furniture-kit
- https://polyhaven.com/a/natural_walnut_veneer
- https://polyhaven.com/a/studio_small_09

程序化芯片、服务塔、权限门、数据仓库、队列、模型网络和容器都在`runtime/components.js`，是解释性造型，非制造模型。工作站模型当前使用monitor；键盘/鼠标作为同系列可选资产包含，不声称已出现在所有示例。

没有包含数字人、人像、声音、业务截图、Microsoft Store等品牌标记或真实源码资料。原始示例的私有云管理和语音克隆代码也不在本包中。
