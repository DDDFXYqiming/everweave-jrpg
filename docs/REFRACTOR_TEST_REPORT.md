# Content Runtime v2 — 本轮交付与验证记录

日期：2026-09-11。基于私密仓库 `DDDFXYqiming/everweave-jrpg` 的 `main` 提交 `8ba5359ace4dea8a47f035d4de959bf7d9120888`。

## 交付状态

完整改造在本轮源码包和 Git 补丁中，**尚未完整推送至 GitHub**。实际调用连接器成功创建了工作分支及准备性提交；上传核心 `engine/runtime.py` 时，平台请求安全检查拦截了写入，返回的不是 GitHub 403。没有推断仓库只读，也没有将缺少关键模块的版本合入 main。临时工作流及不完整的单模块提交已经在工作分支清理，main 保持原提交。

## 实际执行的验证

执行环境：Linux；Python 3.13.5；官方 Godot `4.7.2.stable.official.ed1daf0bf`（通过私密 Actions 产物取得公开官方引擎二进制）。测试对象是本轮修改后的工作目录，不是只运行了原仓库的 CI。

| 检查 | 结果 |
|---|---|
| `python -m unittest discover -s tests -q` | 132 项通过，含原有 99 项和新增 33 项 |
| `python tools/build_content_fixture.py` | `CONTENT_FIXTURE_OK`，实际 Python 行动生成原生测试快照 |
| Godot `--headless --editor --path . --import --quit` | 通过；无脚本、解析或导入错误 |
| `tests/client_smoke.gd` | `GODOT_CLIENT_SMOKE_OK` |
| `tests/visual_compiler_smoke.gd` | `VISUAL_COMPILER_OK geometry_changes_pixels=true` |
| `tests/content_smoke.gd` | `GODOT_CONTENT_SMOKE_OK animated_pixels=true authored_map=true dynamic_actions=true causal_door=true` |
| `GODOT_BIN=... python tools/test_native.py --headless` | `NATIVE_E2E_OK actions=119 maps=1.0`；真实 Godot 客户端和本机 HTTP 服务交互 |
| 原生重建测试 | `NATIVE_REBUILD_OK cancel_preserved=true fresh_epoch=true stale_ignored=true` |
| `git diff --check` | 通过 |
| 发布文件白名单检查 | 通过；不包括密钥、个人存档、引擎二进制或模型响应日志 |

上述是自动化功能、接口和原生冒烟验证，不是 Windows 人工游玩验收，也不证明游戏已经足够好玩。

## 已验证的核心能力

- 模型场景数据决定地图尺寸、地表、房间和实体坐标；不强制套用旧随机地图骨架。
- 对象操作以表达式、状态、事件和效果表示；通用解释器执行，没有测试谜题的专用实现函数。
- 历史位置驱动影子；条件操作改变门的实心状态和像素图形；复合条件完成目标并只奖励一次。
- 自定义战斗操作、消耗、伤害与敌方回合规则进入真实状态；客户端根据可用动作构建按钮。
- 行动计时器、条件目标、地图变形与新图形可保存和读回。
- 非法或超预算执行使整个玩家动作回滚，而不是留下部分奖励。
- 运行时图形配方生成真实像素及动画帧；自定义地表被原生客户端使用。
- 新区域要求 Content v2 协议，拒绝悄悄回退成旧地图；保留旧存档和显式离线自检兼容。

## 未完成或不能据此保证的内容

- **没有运行本轮真实 DeepSeek 在线生成测试，未使用聊天里的临时 API key。** 在线 JSON 质量、延迟、费用、连续生成成功率需在本机实测。
- 没有声称任意新谜题均可解、没有重复或达到专业美术质量；结构签名和设计历史仅辅助减少重复。
- 音乐、基础 UI、部分成长与数值结算仍由引擎实现；本轮开放的是场景、对象和交互程序的表达能力。
- 旧世界已经访问过的地图不会自动变为新蓝图。测试新协议请新建世界，最好使用独立 DataDir。

## 推荐本机试跑

将源码包解压到新目录，把本机 Godot Windows 可执行文件放到项目根目录，然后运行：

```powershell
.\Start.ps1 -DataDir .\userdata\content-v2-test
```

在界面填写一句话设定，选择在线生成并提供本机密钥。`E` 与相邻对象交互；`F` 打开自定义操作；`.` 等待一行动 tick；自定义战斗 `1–9` 选择操作、`Esc` 撤离。

使用补丁时，在原仓库 main 的干净工作区先 `git apply --check`，成功后再 `git apply`。补丁不要求切换到远端准备分支，也不自动提交、推送或覆盖存档。
