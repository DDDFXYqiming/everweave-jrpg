# 快速自主试玩

由测试者根据玩家看到的内容决定目标，`tools/play_session.py` 负责观察、寻路和执行正常动作。它使用现有的本机 HTTP 接口，不增加服务，不替玩家选择解谜方案，也不配置或调用模型。

## 使用

用独立存档启动游戏或仅启动后端。已运行的存档不要再启动第二个实例。

```powershell
python launch.py --server-only --data-dir ./userdata/my-test
```

另一个终端读取当前状态：

```powershell
python tools/play_session.py --data-dir ./userdata/my-test observe
```

从观察结果选择一个真实的对象 ID。下面的 ID 仅为示例，不是固定测试路线：

```powershell
python tools/play_session.py --data-dir ./userdata/my-test go r0:generator --interact
python tools/play_session.py --data-dir ./userdata/my-test choose inspect_generator
python tools/play_session.py --data-dir ./userdata/my-test close
```

其他动作包括 `invoke <当前操作ID>`、`use <物品ID>`、`combat <当前战斗操作ID>`、`interact <相邻对象ID>`、`wait` 和 `enter_exit`。不会自动选择对话、重试失败动作或等待模型生成完成。可使用全局选项 `--record ./userdata/my-test/play.jsonl` 记录公开观察及操作，便于回溯。

## 连续移动的停止条件

寻路只读取当前地图的物理空间，每一步都调用正常 `/action`，经过碰撞、时间、触发器和存档。以下情况立即停止并返回观察：战斗、对话或菜单、地区变化、资源变化、物品/任务/人物或可见对象变化、新日志、实际移动被阻挡、目标不可见、无法到达或步数上限。

`go` 默认最多执行 160 步，可用 `--max-steps` 调整，上限 300。到达交互范围时停止；只有显式带 `--interact` 才继续交互。它不传送玩家、不修改生命、不设置完成旗标。

## 观察和验证边界

观察只输出当前界面可展示的对象、资源、物品、目标、近期记录、战斗数据和当前选项。排除程序、条件表达式、未来场景、隐藏出口、人物内部状态、模型计划与密钥。目前游戏没有房间内战争迷雾，工具因此能看到当前地图上的对象；以后引入视野机制时需同步收窄投影。

HTTP 自动移动检查玩法与后端状态，不验证 Godot 的点击命中、遮挡、键位或渲染。客户端输入继续由 `tools/test_native.py --adventure` 等原生检查覆盖；关键画面单独截取检查。固定回归数据用于验证接口，真实模型世界的探索目标由测试者临场决定，两者应分开报告。

工具不会读取或发送模型密钥，只读取当前存档的本机运行令牌；仅接受 `127.0.0.1`，禁用代理和重定向。超时可能发生在动作已提交之后，因此先重新观察，不自动重放动作。

实际速度与保存文件、地图规模和触发器有关。本轮雾港世界的 8 步移动加交互耗时 0.44 秒，17 步加交互耗时 0.76 秒；这仅是动作执行时间，不含测试者判断和模型生成时间。详细记录见 [冒险验收](ADVENTURE_VALIDATION.md)。
