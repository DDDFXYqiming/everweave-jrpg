# 开发与测试

Python 服务管理世界状态和规则，Godot 客户端负责显示和输入。修改玩法之前可以先阅读 [架构](ARCHITECTURE.md) 与 [内容协议](EXECUTABLE_CONTENT.md)。

## 准备资源

```powershell
python -m engine.asset_cache --download
python -m engine.asset_cache --verify
```

额外素材由索引重建，原始文件不需要加入 Git。扩充素材时应保留来源、许可和兼容信息，方法见 [混合内容库](HYBRID_CONTENT.md)。

## 回归测试

```powershell
python -m unittest discover -s tests -v
```

配置 `GODOT_BIN`，或将引擎放在启动器能找到的位置，再运行原生端到端测试。

```powershell
python tools/test_native.py --content --headless
python tools/test_native.py --hybrid --headless
python tools/test_native.py --adventure --headless
python tools/test_native.py --threat --headless
python tools/test_native.py --generated PATH/to/world.sqlite3 --headless
```

单独检查 Godot 脚本和图形编译可以使用引擎命令行。

```text
godot --headless --editor --path . --import --quit
godot --headless --path . --script res://tests/terrain_materials_smoke.gd
python tools/build_campaign_fixture.py
godot --headless --path . --script res://tests/campaign_client_smoke.gd
```

这些回归使用固定测试数据，不调用在线模型。在线生成验证会消耗服务额度，应使用独立存档和有限的调用预算。请保留失败样本用于排查，不把截图渲染结果当作交互已经成功的证明。

未知世界的自主探索使用 [快速试玩工具](FAST_PLAYTEST.md)：由测试者选择目标，本机连续执行正常动作，在事件处停止。关键画面与原生输入另行验证，避免逐格截图。全局导演、人物关系、跨区技能、实际输入与在线联调记录见 [冒险验收](ADVENTURE_VALIDATION.md)。

已有试玩存档可用 `tools/review_adventure_live.py --live --source PATH/world.sqlite3 --output NEW_DIR --steps 1 --max-calls 2` 做有限联调。脚本用 SQLite 备份到新目录，再运行正常调度器；可能得到导演复盘、地区或委托任务，具体以 trace 为准。

章节专项位于 `tests/test_campaign.py`，覆盖共享状态、图连接、隐藏/锁闭路线、接续、资源和失败模式。客户端专项需要先生成 `userdata/campaign-fixture` 测试数据；这不是在线游戏的备用世界。上一轮验证结果及未试玩部分见 [交付记录](CAMPAIGN_VALIDATION.md)。

## 可选在线联调

下面的命令默认通过 Everweave 的 ChatGPT 订阅直连调用 **GPT-5.6 Luna / high**，无需 API Key。先在游戏中完成设备授权；输出目录必须是未使用的新目录：

```powershell
python tools/test_hybrid_live.py --live --campaign --steps 3 --max-calls 6 --output ./userdata/campaign-check --setting "现代医院停电，我要寻找失联同事并恢复隔离系统。不同地区共享线索，有回环和隐藏通道，不要魔法或等级。"
```

`--steps` 是调度步骤上限，不是保证生成的地区数；每步可能包含修复，`--max-calls` 才是请求预算。复杂新地区默认由两次真实请求并行制作，所以预算至少需要 2；不足时自动使用单请求路径。`--campaign` 启用规划，省略时为单地区路径测试。`--plan-from` 可重放相同设定下 trace 第一条章节响应，再生成地区；必须在报告中区分回放与新请求。`--retry-from` 是原有开局地区修复工具，不用于续修章节计划。

`test_hybrid_live.py` 与 `review_adventure_live.py` 的 `--provider chatgpt_subscription` 为默认值；`codex_subscription` 只保留 App Server 对照。需要有意测试旧 DeepSeek API 时使用 `--provider chat_completions` 并提供 `DEEPSEEK_API_KEY`；没有自动回退。历史 trace 不因默认服务改变而改名或重算。

订阅请求停滞分析优先使用 `tools/diagnose_codex.py`，方法和日志字段见 [Codex 订阅接入](CODEX_SUBSCRIPTION.md) 与 [日志](LOGGING.md)。诊断保持 high 或更高；程序拒绝 medium/low/none，避免测试结论来自降低思考等级。

脚本保存 `trace.json/result.json/snapshot.json` 和独立数据库。`ready` 仅代表当前地区存在，还需检查 `failed_tasks`、`ready_regions` 和各任务记录，不能单凭输出的成功标记判断整章已完成。

## 编辑器与日志

在 Godot 编辑器运行客户端前，可以单独启动本机服务。

```powershell
python launch.py --server-only --data-dir ./userdata/editor-session
```

日志保存在当前存档的 `logs/engine.jsonl`，排查方法见 [日志说明](LOGGING.md)。提交问题时只附必要的错误和复现步骤，检查日志、截图及生成内容中的私人信息。
