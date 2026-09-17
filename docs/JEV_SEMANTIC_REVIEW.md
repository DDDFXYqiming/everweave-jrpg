# Jev 素材筛选与内容语义审查

Everweave 只通过 TypeSafe 官方 Python SDK 调用官方 System One API：

- SDK：`typesafe-sdk==0.6.0`
- API：`https://api.typesafe.ai`
- 模型别名：`jev-latest`
- 凭据：进程级 `TYPESAFE_API_KEY`，不写入存档、设置或日志

## 执行位置

地区本地约定生成后，玩法作者立即启动。Jev 在并行的视听分支里读取已通过技术规则召回的素材元数据，并为每个图形槽从已知 ID 中选择；`draw_original` 是正式结果，不强迫复用。地表合法性、文件哈希、画布范围和素材家族仍由普通代码负责。

玩法与视听组装完成并通过 Schema、引用、地图、规则、奖励和事务检查后，内容审查器提取三类玩家入口：

- `region.program.actions`
- `region.scenes[].choices`
- 普通 NPC 的 `choices`

每个证据单元保留稳定内容 ID、JSON 路径、玩家文字、出现条件、直接效果、相关 hook、objective 与定义。Jev 分别判断文字/后果和提示/条件；结果只进入观察报告，不抛出 `InvalidPatch`，因此不会触发整个地区的修复循环。

## 失败与计量

关闭 Jev、缺少 SDK、缺少凭据、超时或服务失败都不会阻止地区生成：

- 素材筛选回退到原有有界目录；
- 内容审查记录为 `disabled`、`unavailable` 或 `error`，不记作通过；
- Luna 生成调用与 Jev 判断调用、tokens、失败和疑点分别计量；
- 结果绑定问题版本与完整状态哈希，只在进程内缓存；状态变化后不会复用旧判断。

## 2026-09-17 官方服务实测

使用工作区 DPAPI 密文临时加载凭据，真实官方响应模型为 `jev-1.13.0`。

| 场景 | 请求 | 输入 tokens | 输出 tokens | 结果 |
| --- | ---: | ---: | ---: | --- |
| 轨道气象站槽位素材选择 | 1 | 8,674 | 1,110 | 返回 14 个按槽位候选；未知素材 ID 为 0 |
| 成对检查“交一张却扣两张”与“两人交两张并扣两张” | 1 | 1,035 | 92 | 前者为 `contradicted`，正常反例为 `consistent`，路径分别保留 |

这些数字是一次真实样本，不是生产延迟或准确率保证。`confidence` 只表示该次答案分布的集中程度；上线阈值仍需用成对的错误样本与正常反例校准。

## 2026-09-17 游戏内端到端实机

另用 `userdata/jev-live-e2e-20260917` 独立存档启动真实 Godot 4.7.2 客户端、本机服务、ChatGPT 订阅 Luna/high 与 TypeSafe 官方服务。首区最终生成并加载为 36×20 的“对接环与维护气闸”。

- JEV 素材筛选实际使用 10,798 输入 / 1,238 输出 tokens；对 enemy、building、focal、hero、kestrel_ai 等槽位选择原创缺口。最终 10 个 sprite 均为题材一致的原创像素配方，没有强行采用中世纪候选。
- 同状态地区重试命中 `cached=true`，没有再次调用 JEV。实机发现旧计量会重复累计缓存保存的 usage，现已改为只有 `requests > 0` 才累计 tokens，并有回归测试。
- 首版内容证据漏掉 `op:scene` 引用的具体场景，也没说明 action 目标由运行时预先绑定，造成两个低置信度误报。补齐证据并升级到 `everweave-effects-v4` 后，真实地区复审共 11 项判断，10 项 `consistent`；只保留 `activate_kestrel` 的 prerequisite 疑点。
- 该 prerequisite 疑点进一步暴露真实运行时缺陷：动作 availability 读取 `event.target` 时没有候选 action 自己的 invoke 上下文。`Runtime.available()` 现会在判断时注入候选 action/target，并在结束后恢复原事件。
- 重启同一存档后，角色实际从 `(5,9)` 走到 `(11,10)`，凯斯特尔动作菜单显示 `activate_kestrel enabled=true`。进入场景前电池/氧气为 8/100；选择“接受筛选摘要”后实际变为 7/98，与显示的“消耗1格电池、2点氧气”一致。

这次验收还经历了一次真实的 ChatGPT SSE transient connection failure。地区事务未提交且没有自动重试风暴；一次显式地区重试复用了 JEV 缓存并成功完成。最终全量 Python 回归为 328 tests passed。
