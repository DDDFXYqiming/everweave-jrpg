# 引擎日志

正常启动时自动写入当前存档目录的 `logs/engine.jsonl`。使用 Python 标准库 `logging` 与 `RotatingFileHandler`，单文件 5 MiB，最多保留 3 个轮转备份。

每行是一个 JSON 事件，含 UTC 时间、级别、运行 ID、进程、线程、事件名及结构化数据。记录服务器启停、配置摘要、模型请求/响应耗时与 usage、校验错误与纠正、失败/过期/应用、定向重试，以及真实 HTTP 游戏动作的前后位置与数值。异常包含堆栈。

高频 `/state` 轮询不写日志。默认不记录完整提示词、模型正文、HTTP 头或配置中的密钥；已知 API key、本机令牌和常见凭据格式会脱敏。日志只保存在本机，`userdata/` 不进入 Git。

排查时先通过画面复现，再按时间、动作、地区 ID 或 `request_id` 查找 `action.completed`、`action.rejected`、`model.response`、`generation.rejected`、`generation.failed` 等事件。日志提供执行证据，不作为替玩家选择探索路线或解谜答案的接口。

ChatGPT 直连记录 `chatgpt.request.started`、`chatgpt.reasoning.started`、`chatgpt.output.started`、`chatgpt.progress` 和 `chatgpt.request.finished`。进度包含首个推理/输出时间、累计字符、SSE 事件计数、距最后事件的时间、共享任务剩余时间和最终 usage；不含提示词、令牌或完整模型响应。收到合法的 `response.completed` 后立即结束读取。若连接提前结束，失败记录会注明 `category`、`event_counts`、已收字符数、是否收到完成事件和 `usage_unknown`，半截回答不会进入校验或与下一次回答拼接。旧 App Server 对照模式保留 `codex.*` 事件。

`model.context.prepared` 记录投影前后字符数、系统说明长度、压缩比例、修复说明长度及是否带入被拒结果，用来判断耗时是否来自上下文膨胀；它不记录提示词正文。双路地区另有 `region.context.split`，分别记录玩法、视听、约定的字符数及各类候选素材数量。

## 自动恢复事件

一次生成任务共享 15 分钟总时限，首发、传输补试、组件修复和退避等待都消耗这段时间。默认最多补试一次，且每次真实发送都计入 `max_calls`。只有暂时性连接故障、未收到 `response.completed` 的断流和可重试限流会补试；限流遵守 `Retry-After`。令牌过期最多刷新一次。额度、权限、模型、参数、证书、用户停止和总时限错误直接结束。

`chatgpt.retry.scheduled`、`chatgpt.retry.started`、`chatgpt.retry.exhausted` 依次说明补试原因、等待秒数、前一次调用号、新调用号、半截字符数和剩余总时限。地区双路制作只补试失败的组件，已经完成的另一组件保留在当前任务内存中。补试仍失败时，Director 暂停后续预生成并写入 `director.paused`，等待玩家在失败详情中手动继续。

可能已经发送或开始执行、但未收到最终 usage 的尝试会写入 `usage_unknown=true`，并累计到诊断界面的“失败调用用量未知”。这表示无法从最终事件核对 token，不能解释成零消耗；额度和普通权限等明确的 HTTP 拒绝不会混入这项计数。

直连同时保留 3 分钟无 SSE 事件判定。旧 App Server 对照会在 300 秒位置记录 `codex.previous_deadline.reached`。旧对照模式异常结束时，`logs/codex-partials/` 可保留最多 128 KB 的最终回答增量；commentary 和推理文本不会写入。该目录可能含尚未校验的游戏内容，提交问题前仍应检查其中的故事文本。

Godot 与本机服务断开后，只从启动器指定的 `runtime.json` 重新发现环回地址、令牌与 `instance_id`，按 1、2、4、8、15 秒退避。客户端日志保存在同一数据目录的 `logs/client.jsonl`，达到 1 MiB 后从新的轮转标记继续。`client.connection.*` 记录断开、发现和恢复；`client.action.not_replayed` 说明结果未知的动作未被自动重放；新服务实例会重置快照序号基线，迟到的旧实例结果会被丢弃。

单次复现可使用：

```powershell
python tools/diagnose_codex.py --live --source PATH/world.sqlite3 --output NEW_DIR --timeout-seconds 900
```

该工具固定模型为 `gpt-5.6-luna`，默认思考等级为 `high`，可传入 `--effort medium`。默认 `--transport direct`，只复制存档并执行一个待调度任务。标准输出仅显示阶段和计数；详细事件在新目录的日志中。`--transport app-server` 只用于历史路径对照。它不会读取其他项目的授权，也不会调用 DeepSeek。
