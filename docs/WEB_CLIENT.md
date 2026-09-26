# Godot Web 游戏界面

浏览器与 Windows 客户端运行同一套 `client/main.tscn`、`client/ui/game_hud.tscn`、地图绘制、菜单、音频和交互代码。Python 本机服务仍负责 LLM 生成、规则执行与 SQLite 存档。Web 入口只负责交付 Godot 的 WebAssembly 导出文件，没有另外实现一套 HTML 游戏界面。

```powershell
python launch.py --web --data-dir ./userdata/web-journey
```

也可双击 `Start-Web.cmd`，或用 PowerShell 7 执行 `./Start.ps1 -Web -DataDir ./userdata/web-journey`。启动器会准备素材、导入 Godot 工程、在该存档目录的 `web-export/` 生成 Web 导出，然后打印 `http://127.0.0.1:端口`。每次启动都会重新导出当前工程；不同存档各有自己的导出文件，不会相互覆盖。需要固定端口时加 `--port 61012`。

在连接页填入第三方服务的 API Key 并成功应用后，服务会按完整 URL 把它保存在项目内的 `userdata/provider-keys.local.json`。重启后，同一 URL 的 Key 可以留空复用；改用其他 URL 时不会自动带上旧 Key。该文件被 Git 忽略，`userdata/.gdignore` 也使它不进入 Godot 导出包；游戏状态接口不返回 Key。

Web 导出需要与工程匹配的 Godot Standard 可执行文件。首次缺少导出模板时，启动器从 Godot 官方发布包按需安装当前版本的单线程 Web 模板；此后直接复用。可以用 `--godot` 指向已安装的 Godot。导出产物和模板都不提交到项目 Git。

只想检查界面和动作、不调用模型时，可使用独立测试存档：

```powershell
python launch.py --web --demo --data-dir ./userdata/web-demo
```

浏览器内依然是原 Godot 操作：WASD 移动，E 交互，F 动作，Esc 暂停；连接页可选择 Luna 模型和 Off、Low、Medium、High、XHigh、Max 六档。`--demo` 使用固定离线内容；正常在线模式在玩家选择并开始旅程后才会调用订阅模型。

本机服务只监听 `127.0.0.1`。Web 页面由同一服务提供，浏览器保存本次进程的 HttpOnly、SameSite cookie；Godot Web 客户端通过同源请求调用原动作 API，不读取或传输原生客户端的 Bearer 令牌。原生客户端仍使用其已有的启动器令牌。两端收到相同的世界快照，所以浏览器测试能直接覆盖玩家实际看到的 HUD 与画面。服务重启后刷新浏览器页面可取得新会话 cookie；存档仍由启动器独占锁保护。

Godot Web 运行在浏览器 Canvas 中，因此浏览器自动化需要按实际画面操作，不能依赖旧 HTML 试玩界面的 DOM 按钮。浏览器需支持 WebAssembly 和 WebGL 2.0；音频通常要先有一次用户点击。浏览器标签页的后台暂停和原生窗口行为也会有所差异，但游戏 UI、渲染代码和动作逻辑是同一份。

之前的 [Web 实测报告](WEB_LIVE_REVIEW_2026-09-22.md) 属于已移除 HTML 包装层的阶段记录，其模型耗时和规则日志仍保留作历史对照。
