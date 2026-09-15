# 引擎日志

正常启动时自动写入当前存档目录的 `logs/engine.jsonl`。使用 Python 标准库 `logging` 与 `RotatingFileHandler`，单文件 5 MiB，最多保留 3 个轮转备份。

每行是一个 JSON 事件，含 UTC 时间、级别、运行 ID、进程、线程、事件名及结构化数据。记录服务器启停、配置摘要、模型请求/响应耗时与 usage、校验错误与纠正、失败/过期/应用、定向重试，以及真实 HTTP 游戏动作的前后位置与数值。异常包含堆栈。

高频 `/state` 轮询不写日志。默认不记录完整提示词、模型正文、HTTP 头或配置中的密钥；已知 API key、本机令牌和常见凭据格式会脱敏。日志只保存在本机，`userdata/` 不进入 Git。

排查时先通过画面复现，再按时间、动作、地区 ID 或 `request_id` 查找 `action.completed`、`action.rejected`、`model.response`、`generation.rejected`、`generation.failed` 等事件。日志提供执行证据，不作为替玩家选择探索路线或解谜答案的接口。

Codex 订阅模式额外记录 `codex.request.started`、`codex.stage`、`codex.reasoning.started`、`codex.output.started`、`codex.progress`、`codex.upstream.error`、`codex.turn.completed` 和 `codex.request.finished`。进度含首个推理/输出时间、累计字符、最后事件距今时间、重试/错误数、最终有效上下文窗口和事件计数；不含推理正文、提示词、认证信息或完整模型响应。

旧的 300 秒位置会记录 `codex.previous_deadline.reached`，便于判断当时是否仍有增量。真正的停滞采用连续无事件时间判定。异常结束时，`logs/codex-partials/` 可保留最多 128 KB 的最终回答增量用于判断截断位置；commentary 和推理文本不会写入。该目录可能含尚未校验的游戏内容，提交问题前仍应检查其中的故事文本。

单次复现可使用：

```powershell
python tools/diagnose_codex.py --live --source PATH/world.sqlite3 --output NEW_DIR --timeout-seconds 900
```

该工具固定 `gpt-5.6-luna / high / codex_subscription`，只复制存档并执行一个待调度任务。标准输出仅显示阶段和计数；详细事件在新目录的日志中。它不会调用 DeepSeek。
