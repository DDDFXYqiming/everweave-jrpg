# Everweave · 未写之境

> 让模型写出一章可以走进去的冒险。

[English README](README.en.md)

## 它的特别之处

**章节先于地图**

在线创建世界时，模型先生成游戏规格和章节计划。计划包含本章目标、4 至 8 个地区、双向连接、分支、回环、锁闭或隐藏路线、共享旗标和下一章接续点。地图中的路线来自这份计划，每个地区沿用计划给出的路线锚点。

**模型生成可执行内容**

模型生成 `scene`、`program`、`visuals` 和 `audio`。其中的 `program` 是受限的规则 DSL，可以读取对象状态、章节旗标、资源、物品和近期位置历史，表达机关、资源交换、战斗条件和依赖历史的谜题。模型提交 JSON，Python 运行时校验并执行规则，Godot 显示结果。

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

完整一章的跨地区通关、任意生成谜题的可解性、题材素材覆盖和长期生成质量仍需要在真实存档中继续检查。在线生成可能需要数分钟，也会产生模型服务费用。首次体验建议使用新的独立存档。

## 游戏画面

下面的截图来自 Godot 客户端实际渲染，展示项目当前可以生成的场景方向。它们用于观察画面和内容组合，不代表每次在线生成都能完成整章。

![潮雾港的修船村](docs/showcase/harbor.png)

| 地下天文馆 | 轨道气象站 |
|---|---|
| ![地下天文馆](docs/showcase/ruins.png) | ![轨道气象站](docs/showcase/orbital.png) |

更多场景说明见 [示例世界](docs/SHOWCASE.md)。

## 快速开始

需要 Python 3.11 或更高版本，以及 Godot 4 Standard。项目当前使用 Godot 4.7.2 测试。

Windows 用户可以把 Godot 可执行文件放在项目根目录或 `tools/`，然后双击 `Start.cmd`。也可以从命令行启动。

```powershell
python launch.py --godot ./tools/Godot.exe
```

如果 Godot 已加入 PATH，运行 `python launch.py` 即可。首次启动会按固定清单准备素材并核对 SHA-256。缺少 Pillow 时，启动器会把相关工具安装到 `userdata/library-tools`，不修改系统 Python 环境。

## 创建世界

在游戏设置中选择 DeepSeek，或填写兼容 Chat Completions 与 JSON 输出的模型服务。API Key 可以在设置中输入，也可以通过 `DEEPSEEK_API_KEY` 环境变量提供。

在线新建世界会先生成游戏规格和章节计划，再生成开局地区。请求次数、思考等级和预算都可以在设置中调整。生成导演会准备附近地区，失败任务会显示具体错误并提供重试入口。

在线生成会产生模型服务费用。初次创建世界和准备新地区可能需要等待；只想检查安装和操作时，可以运行不调用模型的离线自检。

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
| 等待 | `.` |
| 选择战斗操作 | 数字键，具体动作以界面为准 |
| 关闭面板 | Esc |
| 全屏 | F11 |
| 音乐开关 | M |

## 文档

- [使用指南](docs/LOCAL_SETUP.md) 说明安装、模型连接和存档目录
- [运行时架构](docs/ARCHITECTURE.md) 说明 Godot 客户端、本机服务和生成调度
- [章节与游戏规格](docs/CAMPAIGNS.md) 说明章节计划、共享线索、连接图和可选系统
- [内容协议](docs/EXECUTABLE_CONTENT.md) 说明场景、规则和可执行效果
- [混合内容库](docs/HYBRID_CONTENT.md) 说明素材引用、材质、音频和扩库方式
- [示例世界](docs/SHOWCASE.md) 记录实际生成的场景与截图
- [语言设置](docs/LOCALIZATION.md) 说明简体中文与 English 的界面和生成语言
- [开发与测试](docs/DEVELOPMENT.md) 说明资源准备与回归测试
- [安全边界](docs/SECURITY.md) 说明本机服务、凭据和生成内容的限制
- [文档目录](docs/README.md) 汇总使用说明、设计文档和实验记录

## 开发检查

```powershell
python -m unittest discover -s tests -v
python -m engine.asset_cache --verify
```

在线联调会消耗模型服务额度，建议使用独立的 `--data-dir`。运行时密钥、个人存档和生成日志不应提交到仓库。

## 许可

项目自有代码和文档采用 [MIT License](LICENSE)。第三方素材保留各自许可证，来源及作者见 [素材署名](assets/library/CREDITS.md)。完整说明见 [授权说明](LICENSE-NOTICE.md)。
