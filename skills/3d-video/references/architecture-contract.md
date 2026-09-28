# `architecture.json` 合同

完整机器可读schema由`node scripts/schema.mjs`输出；构建脚本执行同一套严格验证，不忽略未知字段。

| 顶层字段 | 内容 |
|---|---|
| `version` | 固定1 |
| `title` | 项目/架构简名，最多48字符 |
| `duration` | 8—180秒 |
| `theme` | `space`或`light` |
| `sources` | `{id,locator,note}`；相对源码位置或文档URL；不含密钥 |
| `groups` | `{id,label,surface}`；surface=`wood`或`none` |
| `nodes` | `{id,label,detail,type,group,position,status,evidence}` |
| `edges` | `{id,from,to,label,kind,evidence,via?}` |
| `flows` | `{id,edges,start,end}`；一个flow是一个连续可追踪的信号 |
| `camera` | `{time,targets,yaw,pitch,distance?}`；从0到duration完整覆盖 |

节点：

- `id`是小写slug，全工程唯一；label最多16字符、detail最多32字符。
- `type`为`client/service/database/agent/gate/cluster/queue/storage`之一。
- `position`是地面平面`[x,z]`，每坐标在-40至40；高度由组件模型决定。
- `status`=`implemented/planned/illustrative`。`illustrative`明确显示“示意”；`planned`显示“规划”并弱化材质。
- `evidence`是sources中的ID数组；不可空。

关系：

- `kind`=`request/event/result/planned`，必须引用存在且不同的端点。
- `via`可选`[[x,y,z],...]`，用于避开别的实体；坐标绝对于同一个场景。
- 相邻反向边自动偏移；允许循环flow，但每个相邻edge的前终点必须等于后起点。
- planned关系不可作为已发生的flow。flow时间窗必须位于视频内。
- 节点物理位置需让线路可读；工具检查逻辑连续性，不擅自证明所有路径无实体遮挡。

相机：targets是节点ID数组。缺省distance根据目标包围范围推导，显式distance在10—120间。相邻pose之间用平滑插值，不弹簧跳动。第一个time必须0、最后一个等于duration，时间严格递增。

自定义图标/模型：在`runtime/components.js`中添加一个明确类型和对应schema枚举、样例、授权记录；不支持任意网络模型路径或脚本注入。常规换项目只编辑JSON，不改运行时。
