# 本机安装与验证（2026-09-11）

项目路径 `<project-root>`，来源为用户下载的 `everweave-jrpg.zip`（70 项测试版本）。

## 启动

双击根目录 `Start.cmd`，填写世界设定，选择“DeepSeek · 在线生成”，点击创造世界。
API key 框可留空，启动器会自动读取本机加密凭据。默认单次启动最多 60 次模型请求。

- Python 3.12.10：使用本机现有安装，游戏运行全部使用标准库，无需 pip 依赖。
- Godot 4.7.2 Standard：安装在 `tools/`，启动器自动发现，已与官方 SHA512 清单核对。
- 模型 `deepseek-flash`，接口 `https://api.deepseek.com`，JSON mode，默认开启 `low` 思考，可在界面调整。
- `deepseek.local.key` 使用 Windows DPAPI 加密，只适用于当前 Windows 用户；Git 已忽略 `*.key`。替换 key 时可在游戏中填写，环境变量 `DEEPSEEK_API_KEY` 优先于本地凭据。
- 正式存档在 `%LOCALAPPDATA%\EverweaveJRPG`；联调存档及原生截图在 `userdata/live-validation/`，与正式存档分开。

## 实际验证

后续引擎优化及最新验收见 [ENGINE_REVIEW.md](ENGINE_REVIEW.md)，下列为首次安装时的记录。

- Python 测试 70 项通过。重复运行时曾有一次超大 HTTP 请求测试触发 Windows 连接中止，重跑通过；该平台偶发问题未归因于模型提示词修改。
- Godot 原生客户端冒烟检查输出 `GODOT_CLIENT_SMOKE_OK`；单独测试脚本退出时有资源残留提示，完整启动器的 headless 检查正常退出。
- 完整启动器完成导入、本地后端启动、客户端连接和退出清理。
- 真实 DeepSeek 开场生成通过；世界反应修正请求格式后通过，地图 revision 从 0 增至 1。
- Godot 使用本机 RX 7800 XT / OpenGL 实际渲染真实生成地图，截图 `userdata/live-validation/native.png`。
- 共发出 8 次真实 API 请求（包括失败与修复尝试），累计返回 usage 为输入 22,821、输出 6,614 tokens；没有使用后台无限重试。

## 本次适配

- 修正 UTF-8 源文件在 Windows GBK 默认编码下的测试读取。
- 修正 `world_view.gd` 鼠标坐标的类型推断编译错误。
- 明确模型反应的 JSON 外壳、对话数组及新实体 ID 格式，保留原有严格校验。
- 统一 CMD / PowerShell 启动入口，自动解密本地 key，启用 Python UTF-8。

官方依据：[Godot 4.7.2](https://godotengine.org/download/archive/4.7.2-stable/)；[DeepSeek API](https://api-docs.deepseek.com/)。
