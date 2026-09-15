# Codex 订阅接入 · GPT-5.6 Luna / high

当前默认生成服务为 `chatgpt_subscription`，模型固定 `gpt-5.6-luna`，思考等级固定 `high`。Everweave 使用独立设备 OAuth，直接读取 ChatGPT Codex Responses SSE，不向 OpenAI Platform API 提交 API Key。官方区分 [ChatGPT 订阅登录与 API Key 按量登录](https://learn.chatgpt.com/docs/auth)。直连实现参考同机 Loreweaver 已验证的订阅适配；该 ChatGPT 后端不是官方文档面向普通第三方应用承诺的公共 API，若上游协议改变，需要同步维护。

## 使用

在游戏连接页完成一次授权：

```powershell
.\Start.ps1
```

连接页默认选择“ChatGPT 订阅直连 · GPT-5.6 Luna”，不显示密钥输入框。点击登录后显示设备代码并打开官方授权页；完成后后台自动保存。继续旅程时使用新配置，世界和存档格式不因服务切换而重建。旧 `codex_subscription` 设置自动迁移到直连；主动选择并保存的 API 模式仍会保留。

订阅模式共享 ChatGPT/Codex 使用额度，并非无限请求，也不能据此保证固定生成速度。请求固定发送 Luna / high，响应若报告其他模型便拒绝；认证、额度或响应失败会停止，绝不自动切换其他模型或收费 API，也不自动购买或申请额外额度。

DeepSeek/兼容 API 是手动选项。PowerShell 启动器默认不解密 `deepseek.local.key`；只有显式 `-LoadDeepSeekKey` 才加载它。订阅模式即使收到 API Key 字段也不会使用。

旧 App Server 对照仍可通过测试工具的 `--provider codex_subscription` 调用，并可用 `EVERWEAVE_CODEX_BIN` 指定可执行文件。正常游戏不再需要 Codex CLI。

## 接入边界

`engine/chatgpt_provider.py` 直接发送无工具的 Responses 请求，`store=false`，通过 SSE 收集 `response.output_text.delta`，直到 `response.completed` 后才进入游戏契约。稳定系统提示使用 `prompt_cache_key`，无工具流程不请求加密推理回放。

授权由 `subscription_auth.py` 管理。Windows 上访问与刷新令牌通过当前用户 DPAPI 加密，默认保存到 `%LOCALAPPDATA%/EverweaveJRPG/chatgpt-subscription.bin`；不写入世界存档、仓库或日志。Everweave 不读写 Codex `auth.json`，也不改全局 `config.toml`。

只收集最终回答，排除中间 commentary 与重复流片段；用量读取 Codex 的 token 通知。对“完整值已经结束，只漏掉末尾少量容器括号”的情况，可补齐最多四个闭合括号，并记录 `closed_json_containers`；字符串被截断、缺少值或括号错配仍失败。之后继续通过原有完整游戏契约校验，绝不自动填写场景、物品或规则。

直连请求使用 15 分钟硬上限和 3 分钟 SSE 无数据上限；只要仍有事件就不会因总时长达到 300 秒而被误杀。连接错误和超时不自动重放；若未收到最终用量，零统计值不表示请求没有消耗订阅额度。

Responses SSE 持续提供回答增量。游戏不会把未完成的机械 JSON 展示或应用给玩家，因为对象引用、地图碰撞和奖励需要整包事务校验；生成详情显示正在推理或已接收字符数。请求使用 JSON Object 模式，最终仍通过完整游戏契约。

## 开发测试

主测试工具默认使用订阅，也可以显式指定：

```powershell
python tools/test_hybrid_live.py --live --provider chatgpt_subscription --campaign --steps 2 --max-calls 4 --output ./userdata/luna-trial --setting "雨夜里，一名佣兵护送掌握秘密的医护人员穿过封锁线。先谈条件，保留交涉、绕路和应战选择。"
```

`review_adventure_live.py` 同样支持该 provider。仍需明确 `--live`，所有请求计入测试预算。只有显式 `--provider chat_completions` 并提供对应密钥才会测试旧 DeepSeek 接口。

## 2026-09-15 初次接入结果

- 本机 `codex login status` 显示 ChatGPT 登录；App Server 返回 Pro，模型列表确认 `gpt-5.6-luna` 支持 high。测试后登录方式保持不变。
- 一次极小 JSON 传输测试成功，耗时约 **6.6 秒**，记录的输入为 3202、输出为 9 tokens。这只证明通道连通。
- 游戏内容初次试跑进行了 **4 次实际模型请求**：前两次章节输出都漏了末尾括号；本地补齐后暴露多余字段，第三次定向修复使章节计划通过。第四次首地区请求达到本地旧 300 秒总时限，被停止，当时没有阶段日志可以判断是否仍活跃。
- 另有一次 App Server 在加载进程级 MCP 配置时退出，发生在模型请求开始之前。已修复 CLI 对配置键的兼容问题，并重新验证订阅预检通过。
- 已收到的游戏用量合计输入 **19627**、输出 **13184 tokens**，不包含超时请求未知的消耗；另有上面的极小传输测试。不能把这些数字当作完整总用量。
- 初次接入时 **295 项 Python 回归通过**。客户端启动、订阅默认项和隐藏密钥输入、语言切换、原生剧情/跨区能力、原内容、混合素材和敌人行为检查通过。订阅失败不落入 HTTP 付费接口的路径有专门测试。

原始结果位于 `userdata/codex-validation/`，包括 `luna-high` 与 `luna-game-final` 的 trace、结果及数据库。它们不提交到 Git。初次结论只证明订阅适配接通，不能证明地区生成完成。

## 超时诊断与复测

参考另一个项目的经验后，先区分 transport：该项目的问题是 `codex exec + communicate()` 将事件缓冲到进程结束；Everweave 从接入开始使用 App Server stdio。新日志实测收到 `item/reasoning/summaryTextDelta` 和 `item/agentMessage/delta`，因此这里没有同一项“完全不流式”故障。游戏不把机械 JSON 增量展示给玩家，但会展示阶段和接收量。

使用同一个尚未生成首区的订阅存档做了一次完整诊断。请求的系统提示约 **22001 字符**、世界上下文约 **6610 字符**；最终输入 **10835**、输出 **15369**、其中推理 **9974 tokens**。连接、登录、模型确认和回合启动约 **2.5 秒**；**9.4 秒**出现推理事件，**186.9 秒**出现首个回答字符，**283.4 秒**完成。期间共有 18 条十五秒进度记录、5315 条回答增量，最后事件距完成约 0.04 秒；上游错误、重试和 stderr 均为 0。

这个结果说明旧 300 秒是总时限，和一次正常完成的地区请求只差约 17 秒。原超时不能证明 Luna 停滞，很可能在仍推理或输出时被本机停止。耗时主要来自 High 对一次“地图＋角色＋规则＋战斗＋像素配方＋音频”的整包设计，以及近 1.5 万输出 tokens；不是 CLI 启动、上下文 272K 或自动压缩。

App Server 的实际 token 通知返回 `modelContextWindow=828400`，对应显式 872000 配置的有效窗口。当前请求只占约一万输入 tokens，每次又是独立临时回合，没有接近压缩阈值。

第一份完整地区随后被契约拒绝：地标包含无害的 `name` 元数据，动作还引用了未定义场景。前者已作为可选显示元数据保留；后者交给原响应定向修复。严格结构化输出直接套开放的地区对象会被上游在 5 秒内拒绝，因此较小的章节、导演和反应使用严格单字符串信封，完整地区保持直接流式，避免转义令大输出继续膨胀。

定向修复保持 Luna / high：**9.0 秒**开始推理、**80.5 秒**开始输出、**196.7 秒**完成；输入 **16762**、输出 **10568**、其中推理 **4070 tokens**，上游错误和重试均为 0。修复后的“黑檐夜市”通过契约并保存，包含 48×28 地图、5 个实体、8 个动作、3 个钩子、2 个目标、16 个图形和一个 2×2 巡逻敌人。快速试玩以 21 次正常移动抵达秋叶并打开谈判操作，Godot 实际渲染通过。

诊断阶段另做一次严格信封极小测试，约 9.6 秒成功；一次不兼容 schema 测试在推理开始前失败。合计调用均为 `codex_subscription / gpt-5.6-luna / high`，没有调用 DeepSeek，也没有降低思考等级。

修正后 **299 项 Python 测试通过**，并通过原生剧情、跨区能力和敌人行为检查。详细本机证据位于 `userdata/codex-diagnostics/`，包含轮转日志、trace、独立数据库、试玩记录和截图，不加入 Git。

当前结论：Luna / high 可以生成并修复可玩地区；一次请求仍可能需要 3～5 分钟。新的 15 分钟硬限制和 3 分钟无事件限制解决“活着却被误杀”，进度日志解决“看似卡死”，结构化信封减少小型规划 JSON 截断。它们不会让 High 本身变快。后续若要明显缩短首区等待，应拆分地区的机制/场景与美术/音频委托并行生成，或扩充相容素材以减少原创像素配方；这属于下一阶段架构优化，需要单独做质量和总额度对照。

## 直连迁移与速度对照

迁移前的 App Server 路径每次执行初始化、账户/模型/额度查询、临时线程和回合协议。迁移后直接进行 OAuth 刷新与 Responses SSE，不启用工具、文件、浏览器或智能体线程。

为避免破坏另一个项目的授权，速度测试只从 Loreweaver 数据库读取仍有效的 access token 到内存；没有复制 refresh token，没有修改其数据库。正式运行使用 Everweave 自己的设备授权。

| 测试 | App Server | 直连 |
|---|---:|---:|
| 极小 Luna/high JSON | 约 9.6 秒 | 约 2.5 秒；启用 JSON Object 后约 3.7 秒 |
| 同一“黑檐夜市”首地区 | 283 秒完成 | 296 秒完成 |

大地区直连首次输出约在 183 秒出现，最终输入 7663、输出 16324、推理 10067 tokens。它虽然完成了 SSE，却在中部产生无效 JSON；现已启用 Responses JSON Object 模式。对照说明直连确实去掉约数秒固定开销，但大型地区的主体耗时是 Luna/high 的推理与 1～1.6 万 token 输出，并非 Codex CLI 进程。后续请求使用按静态系统提示生成的 `prompt_cache_key`，可提高同协议前缀的复用机会；缓存是否命中以服务返回用量为准。

因此，这次迁移优化登录、固定延迟、SSE 可观测性和 JSON 传输可靠性；不能把它描述成首地区从五分钟降到几秒。要继续明显提速，需要将场景/机制和美术/音频拆成可并行、可独立修复的委托，并减少缺少相容素材时的原创绘图数量。

Everweave 独立授权已在 Windows 实测。第一次浏览器确认已换回令牌，但重定向的用户资料目录在原子替换时返回 `WinError 17`；令牌正文从未输出，保存失败。现已增加“DPAPI 密文直接刷新写入”的受限回退并补回归，第二次授权成功。凭据文件为 2386 字节，当前 Windows 用户可以解密，文件字节中不含明文 access token。使用这份独立授权做极小 Luna/high 请求耗时约 **2.9 秒**。

开启 Responses JSON Object 后，对首份无效地区做定向修复：约 **107 秒**开始输出，**232.3 秒**完成，输入 14454、输出 12455、推理 5483 tokens，返回 JSON 本身合法。Luna 使用了 `{"and":[...]}`、`{"eq":[...]}`、`{"not":...}` 简写；这些与正式 `op/args` 结构一一对应，现由本地归一化并保留修正记录。处理后第一份响应直接通过，无须第二次 High 请求，生成的 44×26“黑檐夜市”含 7 个实体和 10 个动作，快速试玩用 16 次正常移动抵达秋叶并打开谈判。

此次迁移和诊断没有调用 DeepSeek。Loreweaver 授权只作为两次直连性能/修复测试的内存 access token 来源；未复制 refresh token，未修改其数据库。正式结果使用 Everweave 自己的授权。

最终 **309 项 Python 测试通过**，Godot 脚本导入以及原生内容、混合素材、剧情/跨区能力、任务界面和敌人行为检查通过。重启本机服务后再次读取到 `phase=ready / provider=chatgpt_subscription / model=gpt-5.6-luna / effort=high`，证明授权不是仅在首次登录进程内有效。
