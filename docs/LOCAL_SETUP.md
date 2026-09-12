# 使用指南

## 安装与启动

准备 Python 3.11 或更高版本，以及 Godot 4 Standard。项目当前使用 Godot 4.7.2 测试。Godot 可执行文件可以放在项目根目录、`tools/`，也可以加入 PATH。

Windows 双击 `Start.cmd`。命令行启动适用于需要指定引擎或存档目录的情况。

```powershell
python launch.py --godot ./tools/Godot.exe --data-dir ./userdata/my-journey
```

Linux 使用同样的 Python 启动器，将 `--godot` 指向对应平台的可执行文件。

首次启动按版本固定的清单准备素材，下载后核对 SHA-256。PNG/OGG 缓存在 `assets/library/blobs/`，源包和可选工具缓存位于 `userdata/`。这些目录不进入 Git。

## 模型连接

在设置的连接页选择 DeepSeek，或填写兼容 Chat Completions 与 JSON 输出的接口。填写 API Key 后应用配置。PowerShell 启动器也支持既有的本地 DPAPI 加密凭据，环境变量 `DEEPSEEK_API_KEY` 优先。

密钥不会写入游戏存档。不要把密钥放进世界设定、代码或问题反馈。更换模型服务时，需要确认新服务对应的密钥与模型名称。

请求次数、思考等级和预算由设置控制。生成导演会提前准备相邻地区，暂停按钮只阻止后续请求，已经发出的请求可能继续完成。失败任务可查看具体错误后重试。

## 存档

每个存档目录保存一个世界，启动器使用独占锁防止两个实例同时写入。另开新世界前，可以通过 `--data-dir` 选择新目录。

默认目录由操作系统决定。Windows 使用 `%LOCALAPPDATA%/EverweaveJRPG`；Linux 使用 `$XDG_DATA_HOME/everweave-jrpg`，未设置时使用用户目录下的 `.local/share/everweave-jrpg`。

游戏内新建世界会替换当前目录中的世界，请留意确认界面。普通移动和交互会自动保存。异常退出后遇到锁文件提示，应先确认原游戏进程已经结束，再处理该目录中的 `instance.lock`。

## 离线自检

```powershell
python launch.py --demo --data-dir ./userdata/offline-demo
```

离线样例用于检查本机运行环境。新内容的在线生成仍需要模型服务。
