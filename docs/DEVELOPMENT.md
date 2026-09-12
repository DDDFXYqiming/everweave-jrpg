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
```

单独检查 Godot 脚本和图形编译可以使用引擎命令行。

```text
godot --headless --editor --path . --import --quit
godot --headless --path . --script res://tests/terrain_materials_smoke.gd
```

这些回归使用固定测试数据，不调用在线模型。在线生成验证会消耗服务额度，应使用独立存档和有限的调用预算。请保留失败样本用于排查，不把截图渲染结果当作交互已经成功的证明。

## 编辑器与日志

在 Godot 编辑器运行客户端前，可以单独启动本机服务。

```powershell
python launch.py --server-only --data-dir ./userdata/editor-session
```

日志保存在当前存档的 `logs/engine.jsonl`，排查方法见 [日志说明](LOGGING.md)。提交问题时只附必要的错误和复现步骤，检查日志、截图及生成内容中的私人信息。
