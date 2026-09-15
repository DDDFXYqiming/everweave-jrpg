# Content Runtime v2 验证记录

日期为 2026-09-11，基于提交 `8ba5359ace4dea8a47f035d4de959bf7d9120888`。

> 历史阶段记录。当前代码已经继续加入章节导演、混合内容、敌人行为和 ChatGPT 订阅直连；本文数字和限制只描述当时版本。

## 实际执行的验证

验证使用 Linux、Python 3.13.5 和 Godot `4.7.2.stable.official.ed1daf0bf`。以下结果对应当时的实现版本。

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

- 该阶段尚未执行真实 DeepSeek 在线生成测试。 在线 JSON 质量、延迟、费用、连续生成成功率需在本机实测。
- 没有声称任意新谜题均可解、没有重复或达到专业美术质量；结构签名和设计历史仅辅助减少重复。
- 音乐、基础 UI、部分成长与数值结算仍由引擎实现；该版本开放的是场景、对象和交互程序的表达能力。
- 旧世界已经访问过的地图不会自动变为新蓝图。测试新协议请新建世界，最好使用独立 DataDir。

当前启动与独立存档方法见 [使用指南](LOCAL_SETUP.md)。
