# 引擎日志

正常启动时自动写入当前存档目录的 `logs/engine.jsonl`。使用 Python 标准库 `logging` 与 `RotatingFileHandler`，单文件 5 MiB，最多保留 3 个轮转备份。

每行是一个 JSON 事件，含 UTC 时间、级别、运行 ID、进程、线程、事件名及结构化数据。记录服务器启停、配置摘要、模型请求/响应耗时与 usage、校验错误与纠正、失败/过期/应用、定向重试，以及真实 HTTP 游戏动作的前后位置与数值。异常包含堆栈。

高频 `/state` 轮询不写日志。默认不记录完整提示词、模型正文、HTTP 头或配置中的密钥；已知 API key、本机令牌和常见凭据格式会脱敏。日志只保存在本机，`userdata/` 不进入 Git。

排查时先通过画面复现，再按时间、动作、地区 ID 或 `request_id` 查找 `action.completed`、`action.rejected`、`model.response`、`generation.rejected`、`generation.failed` 等事件。日志提供执行证据，不作为替玩家选择探索路线或解谜答案的接口。
