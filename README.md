# Everweave · 未写之境

> 让模型写出一章可以走进去的冒险。

[English README](README.en.md)

## 它的特别之处

**章节先于地图**

在线创建世界时，模型先生成游戏规格和眼前 2 至 4 个地区的滚动计划，保留私有的结局方向。中段可以随实际选择追加地点、支线和连接。已有整章模式仍支持 4 至 8 个地区；地图中的路线始终来自真实连接记录。

**全局导演统筹，内容作者制作**

导演定义持续人物、任务依赖、技能简报、资源收益约束与结局条件，具体地区作者落实场景、对白、遭遇和规则。真实事件积累后，导演可追加内容委托、调整尚未到访的地区或补充受限连接。玩家选择影响同一份人物状态，学会的能力可以跨地区使用。

当前目标显示在地图左上角，点击或按 Q 展开行动记录。未发现任务不会进入任务列表、手记或旅图；敌人可由模型选择驻守、巡逻或追击，在本机行动回合中发现玩家并发起遭遇。生成优先准备等待中的出口和附近地区，空复盘不会废弃在途地图。具体效果与边界见 [节奏与玩法验证](docs/PACING_AND_ENCOUNTERS.md)。

**模型生成可执行内容**

模型生成 `scene`、`program`、`visuals` 和 `audio`。章节中的复杂新地区会把玩法与视听分成两条 Luna / high 请求并行制作，再由本机按同一份导演约定组装和完整校验；简单地区和修复仍可一次生成。[地区双路制作管线](docs/REGION_PIPELINE.md)。可选的官方 Jev 接入会在视听分支内按槽位筛选素材，并在硬校验后核对玩家文字与实际效果；它只记录可定位疑点，不改剧情、不触发整区重试。[Jev 接入与验证](docs/JEV_SEMANTIC_REVIEW.md)。其中的 `program` 是受限的规则 DSL，可以读取对象状态、章节旗标、资源、物品和近期位置历史，表达机关、资源交换、战斗条件和依赖历史的谜题。模型提交 JSON，Python 运行时校验并执行规则，Godot 显示结果。

**世界规格会进入游戏本身**

一个世界的规格可以决定玩家称谓、物品和手记名称、资源条、战斗、物品、装备与成长开关，以及失败方式。规格随存档保存，界面和规则一起跟着世界变化。

**玩家造成的变化会留下来**

玩家操作、触发器、奖励和地图变化在 SQLite 事务中一起提交。附近地区可以在后台准备，旅图只显示已经发现的路线。门打开、道路改变、对象换形等反应会留在世界里。

**本地素材和原创绘图一起工作**

本地素材索引、材质配方和原创像素绘图共同参与生成。模型选择适合题材的候选资产，缺少相容图像时补充受限绘图，程序负责按固定种子布置细节、检查哈希并保存版本。音效和短乐句也可以来自本地素材或有界配方。

**模型提出内容，运行时守住边界**

模型输出只能进入受校验的 JSON 内容协议。它不能提交 Python、GDScript 或任意文件路径，也不能发起网络操作。规则在有预算限制的解释器中运行，失败的动作和存档更新会回滚。

## 当前状态

Everweave 仍是一个研究型原型。章节规划、地区生成、规则校验、本地执行、素材组合、旅图和双语界面已经接入同一套项目；自动测试与 Godot 原生检查覆盖了这些功能的主要路径。

完整一章的跨地区通关、任意生成谜题的可解性、题材素材覆盖和长期生成质量仍需要在真实存档中继续检查。在线生成可能需要数分钟，并消耗所选服务的额度。首次体验建议使用新的独立存档。

## 游戏画面

下面的截图来自 Godot 客户端实际渲染，展示项目当前可以生成的场景方向。它们用于观察画面和内容组合，不代表每次在线生成都能完成整章。

![潮雾港的修船村](docs/showcase/harbor.png)

| 地下天文馆 | 轨道气象站 |
|---|---|
| ![地下天文馆](docs/showcase/ruins.png) | ![轨道气象站](docs/showcase/orbital.png) |

更多场景说明见 [示例世界](docs/SHOWCASE.md)。

## 快速开始

需要 Python 3.11 或更高版本，以及 Godot 4 Standard。项目当前使用 Godot 4.7.2 测试。

在线使用官方 Jev 前安装固定版本 SDK：

```powershell
py -3 -m pip install -r requirements.txt
```

Windows 用户可以把 Godot 可执行文件放在项目根目录或 `tools/`，然后双击 `Start.cmd`。也可以从命令行启动。

```powershell
python launch.py --godot ./tools/Godot.exe
```

如果 Godot 已加入 PATH，运行 `python launch.py` 即可。首次启动会按固定清单准备素材并核对 SHA-256。缺少 Pillow 时，启动器会把相关工具安装到 `userdata/library-tools`，不修改系统 Python 环境。

## 创建世界

默认使用 **ChatGPT 订阅直连 · GPT-5.6 Luna / high**。在连接页为 Everweave 完成一次官方设备授权后，游戏直接读取 Responses SSE，不需要 Codex CLI 或 OpenAI API Key；模型或额度不可用时停止，不自动回退到收费服务。[接入与验证说明](docs/CODEX_SUBSCRIPTION.md)

在线新建世界会先生成游戏规格和章节计划，再生成开局地区。请求预算可以在设置中调整；订阅直连固定使用 high，兼容 API 才按服务支持选择思考等级。生成导演会准备附近地区，失败任务会显示具体错误并提供重试入口。

订阅模式与 Codex CLI 共用同一份 ChatGPT 使用额度，用量计入该配额。DeepSeek 与其他兼容 API 仍可手动选择并按其规则计费，启动器默认不加载 DeepSeek 密钥。初次创建世界和准备新地区可能需要等待；只想检查安装和操作时，可以运行不调用模型的离线自检。

Jev 使用独立的 TypeSafe 官方凭据。可把 API Key 以当前 Windows 用户的 DPAPI 密文保存为 `typesafe.local.key`，并在需要本次进程调用官方服务时显式加载：

```powershell
Read-Host -AsSecureString | ConvertFrom-SecureString | Set-Content .\typesafe.local.key
.\Start.ps1 -LoadTypeSafeKey
```

连接页可随时关闭 Jev。SDK、凭据或服务不可用时，素材目录回退到原排序，内容状态明确显示为未审查，不会伪装成通过。

```powershell
python launch.py --demo --data-dir ./userdata/offline-demo
```

每个存档目录保存一个世界。想保留当前旅程并另开一局，可以指定新的数据目录。

```powershell
python launch.py --godot ./tools/Godot.exe --data-dir ./userdata/another-journey
```

## 操作

| 操作 | 按键 |
|---|---|
| 移动 | WASD 或方向键 |
| 与相邻人物、物体或出口交互 | E 或空格 |
| 查看当前可执行操作 | F |
| 物品与记录面板 | I、J |
| 展开旅途地图 | G，或点击小地图 |
| 展开行动记录 | Q，或点击左上角任务卡 |
| 等待 | `.` |
| 选择战斗操作 | 数字键，具体动作以界面为准 |
| 关闭面板 / 旅途菜单 | Esc |
| 旅途状态抽屉 | Tab |
| 开发诊断 | Ctrl+D，或菜单入口 |
| 全屏 | Alt+Enter，或显示设置 |
| 全部声音静音 / 恢复 | M，或扬声器按钮 |

常驻界面只显示地点、关键资源和一行目标；详细状态在旅途抽屉，模型与 JEV 统计在开发诊断。显示与声音页独立控制音乐、环境声、音效和界面音量，静音、音量与全屏偏好会保存在本机。验证记录见 [客户端表现与音频自测](docs/CLIENT_PRESENTATION.md)。

## 文档

- [使用指南](docs/LOCAL_SETUP.md) 说明安装、模型连接和存档目录
- [运行时架构](docs/ARCHITECTURE.md) 说明 Godot 客户端、本机服务和生成调度
- [章节与游戏规格](docs/CAMPAIGNS.md) 说明章节计划、共享线索、连接图和可选系统
- [冒险导演](docs/ADVENTURE_DIRECTOR.md) 与 [本轮验证](docs/ADVENTURE_VALIDATION.md) 说明创作分工及实际完成范围
- [快速自主试玩](docs/FAST_PLAYTEST.md) 用正常游戏动作执行寻路，在事件处停下，由测试者决定下一步
- [内容协议](docs/EXECUTABLE_CONTENT.md) 说明场景、规则和可执行效果
- [混合内容库](docs/HYBRID_CONTENT.md) 说明素材引用、材质、音频和扩库方式
- [示例世界](docs/SHOWCASE.md) 记录实际生成的场景与截图
- [语言设置](docs/LOCALIZATION.md) 说明简体中文与 English 的界面和生成语言
- [开发与测试](docs/DEVELOPMENT.md) 说明资源准备与回归测试
- [安全边界](docs/SECURITY.md) 说明本机服务、凭据和生成内容的限制
- [文档目录](docs/README.md) 汇总使用说明、设计文档和实验记录

## 许可

项目自有代码和文档采用 [MIT License](LICENSE)。第三方素材保留各自许可证，来源及作者见 [素材署名](assets/library/CREDITS.md)。完整说明见 [授权说明](LICENSE-NOTICE.md)。
