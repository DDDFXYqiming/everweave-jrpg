# Codex 订阅接入 · GPT-5.6 Luna / high

当前默认生成服务为 `codex_subscription`，模型固定 `gpt-5.6-luna`，默认思考等级 `high`。游戏通过本机 Codex App Server 使用已有 ChatGPT 登录，不向 OpenAI Platform API 提交 API Key。官方区分 [ChatGPT 订阅登录与 API Key 按量登录](https://learn.chatgpt.com/docs/auth)；集成协议见 [Codex App Server](https://learn.chatgpt.com/docs/app-server)。

## 使用

本机需安装 Codex CLI，并完成 ChatGPT 登录：

```powershell
codex login
codex login status
.\Start.ps1
```

连接页默认选择“Codex 订阅 · GPT-5.6 Luna”，不显示密钥输入框。继续旅程时使用新配置，世界和存档格式不因服务切换而重建。未带 provider 字段的旧连接设置会采用新的订阅默认值；主动选择并保存的 API 模式仍会保留。

订阅模式共享你在 Codex 中的使用额度，并非无限请求，也不能据此保证固定生成速度。游戏会检查 `account/read` 的 ChatGPT 登录类型、`model/list` 中的精确模型和思考等级，以及已报告的使用限制。达到额度或认证失败就停止，绝不自动切换其他模型或收费 API，也不自动购买或申请额外额度。

DeepSeek/兼容 API 是手动选项。PowerShell 启动器默认不解密 `deepseek.local.key`；只有显式 `-LoadDeepSeekKey` 才加载它。订阅模式即使收到 API Key 字段也不会使用。

可通过 `EVERWEAVE_CODEX_BIN` 指定真实 Codex 可执行文件；Windows 不把复杂参数交给 `.cmd` 包装器，而优先定位安装包中的原生程序。本轮验证版本为 Codex CLI **0.154.0**。其他机器的模型权限应以该机器实际登录和模型列表为准。

## 接入边界

`engine/codex_provider.py` 使用 stdio JSON-RPC，先初始化并检查登录，再建立 `ephemeral=true` 的临时任务，发送 `turn/start`。每次生成使用空临时目录、只读权限和进程级配置，关闭 shell、MCP、应用、浏览器、插件及多代理能力；只接受生成内容，不执行生成模型发出的工具或审批请求。

模型、服务方和思考等级由启动回执复核；禁止模型自动回退，使用标准服务速度。游戏不读写 `auth.json`，不提取、复制或保存订阅令牌，不改全局 `config.toml`。若全局配置强制 API 登录，适配器停止并提示，不为试验强改登录类型。

只收集最终回答，排除中间 commentary 与重复流片段；用量读取 Codex 的 token 通知。对“完整值已经结束，只漏掉末尾少量容器括号”的情况，可补齐最多四个闭合括号，并记录 `closed_json_containers`；字符串被截断、缺少值或括号错配仍失败。之后继续通过原有完整游戏契约校验，绝不自动填写场景、物品或规则。

单次请求上限 300 秒。游戏退出时发出取消信号并清理本次子进程。连接错误和超时不自动重放；若未收到最终用量通知，零统计值不表示这次模型没有消耗额度。

## 开发测试

主测试工具默认使用订阅，也可以显式指定：

```powershell
python tools/test_hybrid_live.py --live --provider codex_subscription --campaign --steps 2 --max-calls 4 --output ./userdata/luna-trial --setting "雨夜里，一名佣兵护送掌握秘密的医护人员穿过封锁线。先谈条件，保留交涉、绕路和应战选择。"
```

`review_adventure_live.py` 同样支持该 provider。仍需明确 `--live`，所有请求计入测试预算。只有显式 `--provider chat_completions` 并提供对应密钥才会测试旧 DeepSeek 接口。

## 2026-09-15 实测结果

- 本机 `codex login status` 显示 ChatGPT 登录；App Server 返回 Pro，模型列表确认 `gpt-5.6-luna` 支持 high。测试后登录方式保持不变。
- 一次极小 JSON 传输测试成功，耗时约 **6.6 秒**，记录的输入为 3202、输出为 9 tokens。这只证明通道连通。
- 游戏内容试跑最多进行了 **4 次实际模型请求**：前两次章节输出都漏了末尾括号；本地补齐后暴露多余字段，第三次定向修复使章节计划通过。第四次首地区请求超过 **300 秒**，被停止，未保存可玩首地区，也没有追加重试。
- 另有一次 App Server 在加载进程级 MCP 配置时退出，发生在模型请求开始之前。已修复 CLI 对配置键的兼容问题，并重新验证订阅预检通过。
- 已收到的游戏用量合计输入 **19627**、输出 **13184 tokens**，不包含超时请求未知的消耗；另有上面的极小传输测试。不能把这些数字当作完整总用量。
- **295 项 Python 回归通过**。客户端启动、订阅默认项和隐藏密钥输入、语言切换、原生剧情/跨区能力、原内容、混合素材和敌人行为检查通过。订阅失败不落入 HTTP 付费接口的路径有专门测试。

原始结果位于 `userdata/codex-validation/`，包括 `luna-high` 与 `luna-game-final` 的 trace、结果及数据库。它们不提交到 Git。结论是：**订阅适配已接通，当前 Luna / high 这次尚未顺利完成完整地区生成**。没有把既有 DeepSeek 世界冒充 Luna 生成，也没有为了成功切换到其他模型或降低 high。
