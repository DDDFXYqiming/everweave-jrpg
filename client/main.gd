extends Control
## Thin Godot client: pixel world, controls and presentation. No paid model calls here.
## A single local standard-library Python helper owns state, validation and the director.

const WorldView = preload("res://client/world_view.gd")
const BattleView = preload("res://client/battle_view.gd")
const BG := Color("0c1421")
const PANEL := Color("142235")
const MUTED := Color("9aaac0")
const GOLD := Color("e7c795")
const MINT := Color("83c9be")

var backend_url: String = ""
var session_token: String = ""
var state: Dictionary = {}
var action_http: HTTPRequest
var poll_http: HTTPRequest
var action_busy: bool = false
var poll_busy: bool = false
var action_route: String = ""
var poll_clock: float = 0.0
var move_clock: float = 0.0
var connection_ready: bool = false
var switch_after_action: bool = false
var first_snapshot: bool = true
var retired_epochs: Dictionary = {}
var local_panel: String = ""
var modal_signature: String = ""
var hp_tint: StyleBoxFlat
var music: AudioStreamPlayer
var music_muted: bool = false

var home: Control
var game: Control
var setting_input: TextEdit
var base_input: LineEdit
var model_input: LineEdit
var key_input: LineEdit
var mode_select: OptionButton
var online_settings: VBoxContainer
var custom_fields: GridContainer
var provider_summary: Label
var mode_help: Label
var effort_select: OptionButton
var effort_help: Label
var start_button: Button
var last_action_error: String = ""
var replace_dialog: ConfirmationDialog
var pending_world_configuration: Dictionary = {}
var budget_input: SpinBox
var form_error: Label
var continue_button: Button
var return_button: Button
var title_label: Label
var subtitle_label: Label
var stats_label: Label
var hp_bar: ProgressBar
var mp_bar: ProgressBar
var quest_label: Label
var director_label: Label
var frontier_label: Label
var error_label: Label
var journal_label: Label
var rule_label: Label
var hint_label: Label
var world_view
var modal_overlay: Control
var modal_stack: VBoxContainer
var battle_canvas
var pause_button: Button

func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_configure_theme()
	_read_connection()
	action_http = HTTPRequest.new()
	action_http.timeout = 10
	add_child(action_http)
	action_http.request_completed.connect(_action_complete)
	poll_http = HTTPRequest.new()
	poll_http.timeout = 4
	add_child(poll_http)
	poll_http.request_completed.connect(_poll_complete)
	_build_game()
	_build_home()
	music = AudioStreamPlayer.new()
	music.stream = preload("res://assets/wander.wav")
	music.volume_db = -14
	add_child(music)
	music.finished.connect(func() -> void:
		if not music_muted: music.play()
	)
	home.show()
	game.hide()
	_poll()

func _exit_tree() -> void:
	if is_instance_valid(music):
		music.stop()
		music.stream = null
	if is_instance_valid(action_http): action_http.cancel_request()
	if is_instance_valid(poll_http): poll_http.cancel_request()

func _configure_theme() -> void:
	var font := SystemFont.new()
	font.font_names = PackedStringArray(["Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans CJK SC", "WenQuanYi Zen Hei", "sans-serif"])
	var t := Theme.new()
	t.default_font = font
	t.default_font_size = 16
	t.set_color("font_color", "Label", Color("e6e9e6"))
	t.set_color("font_color", "Button", Color("e5e8e4"))
	t.set_color("font_hover_color", "Button", Color("fff2ce"))
	t.set_color("font_disabled_color", "Button", Color("697b90"))
	t.set_stylebox("normal", "Button", _box(Color("20374a"), Color("395569"), 7))
	t.set_stylebox("hover", "Button", _box(Color("2b4d5b"), MINT, 7))
	t.set_stylebox("pressed", "Button", _box(Color("172d40"), GOLD, 7))
	t.set_stylebox("disabled", "Button", _box(Color("152331"), Color("26394b"), 7))
	t.set_stylebox("normal", "LineEdit", _box(Color("0e1b2b"), Color("345064"), 5))
	t.set_stylebox("focus", "LineEdit", _box(Color("132439"), MINT, 5))
	t.set_stylebox("normal", "TextEdit", _box(Color("0e1b2b"), Color("345064"), 5))
	t.set_stylebox("focus", "TextEdit", _box(Color("132439"), MINT, 5))
	t.set_color("font_color", "LineEdit", Color("ede8d9"))
	t.set_color("font_color", "TextEdit", Color("ede8d9"))
	t.set_color("font_color", "CheckBox", Color("cbd6da"))
	t.set_stylebox("panel", "PanelContainer", _box(PANEL, Color("2a4052"), 8))
	t.set_constant("separation", "VBoxContainer", 9)
	t.set_constant("separation", "HBoxContainer", 10)
	theme = t

func _box(fill: Color, outline: Color, radius: int = 6) -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.bg_color = fill
	s.border_color = outline
	s.set_border_width_all(1)
	s.set_corner_radius_all(radius)
	s.content_margin_left = 14
	s.content_margin_right = 14
	s.content_margin_top = 10
	s.content_margin_bottom = 10
	return s

func _label(parent: Node, text: String, font_size: int = 16, color: Color = Color("e6e9e6")) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", color)
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	parent.add_child(label)
	return label

func _button(parent: Node, text: String, callback: Callable) -> Button:
	var button := Button.new()
	button.text = text
	button.custom_minimum_size.y = 38
	button.focus_mode = Control.FOCUS_NONE
	button.pressed.connect(callback)
	parent.add_child(button)
	return button

func _margin(parent: Node, amount: int) -> MarginContainer:
	var margin := MarginContainer.new()
	for side in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, amount)
	parent.add_child(margin)
	return margin

func _vbox(parent: Node) -> VBoxContainer:
	var box := VBoxContainer.new()
	parent.add_child(box)
	return box

func _read_connection() -> void:
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--backend-url="):
			backend_url = arg.trim_prefix("--backend-url=")
		elif arg.begins_with("--session-token="):
			session_token = arg.trim_prefix("--session-token=")
	if not backend_url.is_empty() and not session_token.is_empty():
		if not backend_url.begins_with("http://127.0.0.1:"):
			backend_url = ""
			session_token = ""
		return
	var folder: String = ""
	if OS.get_name() == "Windows":
		folder = OS.get_environment("LOCALAPPDATA").path_join("EverweaveJRPG")
	else:
		folder = OS.get_environment("XDG_DATA_HOME")
		if folder.is_empty():
			folder = OS.get_environment("HOME").path_join(".local/share")
		folder = folder.path_join("everweave-jrpg")
	var file: String = folder.path_join("runtime.json")
	if FileAccess.file_exists(file):
		var parsed = JSON.parse_string(FileAccess.get_file_as_string(file))
		if parsed is Dictionary:
			backend_url = str(parsed.get("url", ""))
			session_token = str(parsed.get("token", ""))
	# This client must never send its local session credential to a remote hostname.
	if not backend_url.begins_with("http://127.0.0.1:"):
		backend_url = ""
		session_token = ""

func _build_home() -> void:
	home = Control.new()
	add_child(home)
	home.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var background := ColorRect.new()
	background.color = BG
	home.add_child(background)
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var scroll := ScrollContainer.new()
	home.add_child(scroll)
	scroll.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var center := CenterContainer.new()
	center.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	center.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.add_child(center)
	var margins := _margin(center, 28)
	var panel := PanelContainer.new()
	panel.custom_minimum_size.x = 760
	margins.add_child(panel)
	var box := _vbox(panel)
	_label(box, "E V E R W E A V E", 15, MINT)
	_label(box, "未写之境", 37, GOLD)
	_label(box, "不是预先写好的冒险。你走过的地方成为事实，前方的世界继续被创作。", 16, MUTED)
	_label(box, "一句话，成为你的世界", 18)
	setting_input = TextEdit.new()
	setting_input.custom_minimum_size = Vector2(690, 79)
	setting_input.placeholder_text = "描述世界、主角，或一个无法解释的现象……"
	setting_input.text = "一个永远下雨的蒸汽朋克岛国，我是失忆的帝国逃兵。"
	setting_input.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	box.add_child(setting_input)
	_label(box, "世界创作服务", 16)
	mode_select = OptionButton.new()
	mode_select.add_item("DeepSeek · 在线生成", 0)
	mode_select.add_item("其他兼容服务 · 在线生成", 1)
	mode_select.add_item("引擎自检 · 离线样例", 2)
	mode_select.custom_minimum_size.y = 38
	box.add_child(mode_select)
	mode_help = _label(box, "", 13, MUTED)
	online_settings = _vbox(box)
	provider_summary = _label(online_settings, "DeepSeek Flash · 根据你的设定与行动持续创作", 14, MINT)
	custom_fields = GridContainer.new()
	custom_fields.columns = 2
	online_settings.add_child(custom_fields)
	_label(custom_fields, "API 地址", 15, MUTED)
	base_input = LineEdit.new()
	base_input.text = "https://api.deepseek.com"
	base_input.custom_minimum_size.x = 510
	custom_fields.add_child(base_input)
	_label(custom_fields, "模型名", 15, MUTED)
	model_input = LineEdit.new()
	model_input.text = "deepseek-flash"
	custom_fields.add_child(model_input)
	var grid := GridContainer.new()
	grid.columns = 2
	grid.add_theme_constant_override("h_separation", 14)
	grid.add_theme_constant_override("v_separation", 8)
	online_settings.add_child(grid)
	_label(grid, "API Key", 15, MUTED)
	key_input = LineEdit.new()
	key_input.secret = true
	key_input.placeholder_text = "留空使用此服务已有的密钥"
	key_input.custom_minimum_size.x = 510
	grid.add_child(key_input)
	_label(grid, "思考等级", 15, MUTED)
	effort_select = OptionButton.new()
	grid.add_child(effort_select)
	_label(grid, "本次调用上限", 15, MUTED)
	budget_input = SpinBox.new()
	budget_input.min_value = 1
	budget_input.max_value = 1000
	budget_input.value = 60
	grid.add_child(budget_input)
	effort_help = _label(online_settings, "", 13, MUTED)
	_label(online_settings, "模型串行生成；走路和普通战斗不额外请求。设置会保存，密钥不会写入存档。", 13, MUTED)
	mode_select.item_selected.connect(_mode_changed)
	_mode_changed(mode_select.selected)
	replace_dialog = ConfirmationDialog.new()
	replace_dialog.title = "重新生成世界"
	replace_dialog.ok_button_text = "开始新世界"
	replace_dialog.cancel_button_text = "保留当前世界"
	replace_dialog.confirmed.connect(_confirm_new_world)
	replace_dialog.canceled.connect(func() -> void: pending_world_configuration = {})
	add_child(replace_dialog)
	var buttons := HBoxContainer.new()
	box.add_child(buttons)
	start_button = _button(buttons, "创造世界  →", _start_world)
	start_button.disabled = true
	continue_button = _button(buttons, "应用配置并继续", _continue_world)
	continue_button.disabled = true
	return_button = _button(buttons, "返回游戏", _show_game)
	return_button.hide()
	form_error = _label(box, "正在连接本机引擎……", 14, Color("eab59e"))
	_label(box, "WASD / 方向键移动    E 交互    I 背包    J 旅途记录    Esc 设置", 13, MUTED)
	if backend_url.is_empty():
		form_error.text = "先用 Start.ps1 / python launch.py 启动；编辑器调试请先运行 python -m engine.server。"

func _build_game() -> void:
	game = Control.new()
	add_child(game)
	game.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var margin := _margin(game, 16)
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var all := _vbox(margin)
	var header := HBoxContainer.new()
	all.add_child(header)
	var heading := _vbox(header)
	heading.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title_label = _label(heading, "未写之境", 23, GOLD)
	subtitle_label = _label(heading, "正在织出第一片土地", 13, MUTED)
	stats_label = _label(header, "", 16)
	stats_label.custom_minimum_size.x = 220
	stats_label.size_flags_horizontal = Control.SIZE_SHRINK_END
	_button(header, "I 背包", func() -> void: _toggle_panel("inventory"))
	_button(header, "J 记录", func() -> void: _toggle_panel("journal"))
	_button(header, "设置", _show_home)
	var middle := HBoxContainer.new()
	middle.size_flags_vertical = Control.SIZE_EXPAND_FILL
	all.add_child(middle)
	var map_panel := PanelContainer.new()
	map_panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	map_panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
	middle.add_child(map_panel)
	var map_stack := Control.new()
	map_stack.custom_minimum_size = Vector2(600, 440)
	map_panel.add_child(map_stack)
	world_view = WorldView.new()
	map_stack.add_child(world_view)
	world_view.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	world_view.entity_clicked.connect(func(id: String) -> void: _send_action({"op": "interact", "id": id}))
	modal_overlay = Control.new()
	map_stack.add_child(modal_overlay)
	modal_overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	modal_overlay.mouse_filter = Control.MOUSE_FILTER_STOP
	var dim := ColorRect.new()
	dim.color = Color(0.025, 0.04, 0.08, 0.66)
	modal_overlay.add_child(dim)
	dim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var modal_center := CenterContainer.new()
	modal_overlay.add_child(modal_center)
	modal_center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var modal_panel := PanelContainer.new()
	modal_panel.custom_minimum_size.x = 560
	modal_center.add_child(modal_panel)
	var modal_scroll := ScrollContainer.new()
	modal_scroll.custom_minimum_size = Vector2(548, 510)
	modal_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	modal_panel.add_child(modal_scroll)
	modal_stack = _vbox(modal_scroll)
	modal_stack.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	modal_stack.custom_minimum_size.x = 530
	modal_overlay.hide()
	var side_panel := PanelContainer.new()
	side_panel.custom_minimum_size.x = 285
	middle.add_child(side_panel)
	var side_scroll := ScrollContainer.new()
	side_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	side_panel.add_child(side_scroll)
	var side := _vbox(side_scroll)
	side.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	side.custom_minimum_size.x = 250
	_label(side, "旅人状态", 17, GOLD)
	hp_bar = _bar(side, Color("c98791"))
	mp_bar = _bar(side, Color("81afcc"))
	rule_label = _label(side, "", 13, MINT)
	_label(side, "正在发生", 17, GOLD)
	quest_label = _label(side, "", 14)
	_label(side, "世界仍在生长", 17, GOLD)
	director_label = _label(side, "", 13, MINT)
	frontier_label = _label(side, "", 13, MUTED)
	error_label = _label(side, "", 13, Color("e7a69d"))
	var controls := HBoxContainer.new()
	side.add_child(controls)
	pause_button = _button(controls, "暂停导演", _toggle_pause)
	_button(controls, "重试", func() -> void: _post("/retry", {}))
	_label(side, "最近的回声", 17, GOLD)
	journal_label = _label(side, "", 13, MUTED)
	var footer := HBoxContainer.new()
	all.add_child(footer)
	hint_label = _label(footer, "WASD 移动 · E 交互 · I 背包 · J 记录 · 所有进度自动保存", 13, MUTED)
	_button(footer, "M 音乐", _toggle_music)

func _bar(parent: Node, fill: Color) -> ProgressBar:
	var bar := ProgressBar.new()
	bar.custom_minimum_size = Vector2(220, 15)
	bar.show_percentage = false
	bar.add_theme_stylebox_override("background", _box(Color("0a1624"), Color("0a1624"), 3))
	bar.add_theme_stylebox_override("fill", _box(fill, fill, 3))
	parent.add_child(bar)
	return bar

func _configuration() -> Dictionary:
	var custom: bool = mode_select.selected == 1
	return {"offline": mode_select.selected == 2, "base_url": base_input.text.strip_edges() if custom else "https://api.deepseek.com", "model": model_input.text.strip_edges() if custom else "deepseek-flash", "api_key": key_input.text.strip_edges(), "deepseek_options": not custom, "reasoning_effort": str(effort_select.get_item_metadata(effort_select.selected)), "max_calls": int(budget_input.value)}

func _set_effort(effort: String) -> void:
	for i in range(effort_select.item_count):
		if str(effort_select.get_item_metadata(i)) == effort:
			effort_select.select(i)
			return
	effort_select.select(0)

func _mode_changed(index: int) -> void:
	var previous: String = "low" if effort_select.item_count == 0 else str(effort_select.get_item_metadata(effort_select.selected))
	effort_select.clear()
	var efforts: Array = ["low", "high", "max", "none"] if index != 1 else ["low", "medium", "high", "xhigh", "max", "minimal", "none", "default"]
	for effort in efforts:
		var label: String = "关闭思考" if effort == "none" else ("服务默认（不传参数）" if effort == "default" else effort)
		effort_select.add_item(label)
		effort_select.set_item_metadata(effort_select.item_count - 1, effort)
	_set_effort(previous)
	effort_help.text = "默认 low；可随时调整思考等级，应用后用于后续生成。" if index != 1 else "等级由接入服务支持；不接受此参数的服务请选择“服务默认”。"
	online_settings.visible = index != 2
	custom_fields.visible = index == 1
	provider_summary.visible = index == 0
	key_input.text = ""
	mode_help.text = "从一句设定开始，由模型生成世界并持续续写。" if index != 2 else "仅检查地图、交互与存档功能。内容来自固定测试样例，不调用 LLM。"
	key_input.placeholder_text = "留空使用此服务已有的密钥"
	if index == 0: key_input.placeholder_text = "留空使用启动器加载的 DeepSeek 密钥"

func _sync_configuration() -> void:
	var cfg: Dictionary = state.get("configuration", {})
	if cfg.is_empty(): return
	base_input.text = str(cfg.get("base_url", "https://api.deepseek.com"))
	model_input.text = str(cfg.get("model", "deepseek-flash"))
	budget_input.value = int(cfg.get("max_calls", 60))
	var index: int = 2 if bool(cfg.get("offline", false)) else (0 if base_input.text == "https://api.deepseek.com" and model_input.text == "deepseek-flash" and bool(cfg.get("deepseek_options", true)) else 1)
	mode_select.select(index)
	_mode_changed(index)
	_set_effort(str(cfg.get("reasoning_effort", "low")))

func _start_world() -> void:
	if action_busy: return
	var setting: String = setting_input.text.strip_edges()
	if setting.length() < 3 or setting.length() > 600:
		last_action_error = "世界设定需要 3～600 个字符。"
		form_error.text = last_action_error
		return
	var config := _configuration()
	config["setting"] = setting
	config["replace_save"] = bool(state.get("started", false))
	if config.replace_save:
		pending_world_configuration = config
		replace_dialog.dialog_text = "将按以下设定从头生成新世界：\n\n" + setting.left(180) + "\n\n当前世界及进度会被替换。取消可保留原世界。"
		replace_dialog.popup_centered(Vector2i(560, 250))
		return
	_submit_world(config)

func _confirm_new_world() -> void:
	if pending_world_configuration.is_empty() or action_busy: return
	var config := pending_world_configuration
	pending_world_configuration = {}
	_submit_world(config)

func _submit_world(config: Dictionary) -> void:
	last_action_error = ""
	switch_after_action = true
	_post("/start", config)

func _continue_world() -> void:
	if action_busy: return
	switch_after_action = true
	_post("/configure", _configuration())

func _show_home() -> void:
	local_panel = ""
	_sync_configuration()
	home.show()
	game.hide()
	return_button.visible = bool(state.get("started", false))

func _show_game() -> void:
	if not bool(state.get("started", false)): return
	home.hide()
	game.show()
	get_viewport().gui_release_focus()
	if not music_muted and not music.playing: music.play()
	_render()

func _toggle_music() -> void:
	music_muted = not music_muted
	music.stream_paused = music_muted
	if not music_muted and not music.playing: music.play()

func _toggle_pause() -> void:
	var d: Dictionary = state.get("director", {})
	_post("/pause", {"paused": not bool(d.get("paused", false))})

func _toggle_panel(name: String) -> void:
	if state.get("battle") is Dictionary or not state.get("ui", {}).is_empty(): return
	local_panel = "" if local_panel == name else name
	modal_signature = ""
	_render_modal()

func _headers() -> PackedStringArray:
	return PackedStringArray(["Content-Type: application/json", "Authorization: Bearer " + session_token, "X-Request-ID: " + str(Time.get_ticks_usec()) + "-" + str(randi())])

func _poll() -> void:
	if poll_busy or backend_url.is_empty() or session_token.is_empty(): return
	poll_busy = true
	var result: Error = poll_http.request(backend_url + "/state", PackedStringArray(["Authorization: Bearer " + session_token]))
	if result != OK:
		poll_busy = false
		_connection_error("无法请求本机引擎。请检查启动窗口。")

func _post(route: String, body: Dictionary) -> void:
	if action_busy: return
	if backend_url.is_empty() or not connection_ready:
		_connection_error("本机引擎尚未连接。请通过启动脚本运行。")
		switch_after_action = false
		return
	action_busy = true
	start_button.disabled = true
	continue_button.disabled = true
	action_route = route
	var result: Error = action_http.request(backend_url + route, _headers(), HTTPClient.METHOD_POST, JSON.stringify(body))
	if result != OK:
		action_busy = false
		switch_after_action = false
		_connection_error("动作未能发送。")

func _send_action(body: Dictionary) -> void:
	_post("/action", body)

func _decode(result: int, code: int, body: PackedByteArray) -> Dictionary:
	if result != HTTPRequest.RESULT_SUCCESS:
		return {"error": "本机连接中断；没有自动重发动作，避免重复扣款。"}
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if not parsed is Dictionary:
		return {"error": "引擎返回了不可解析的响应。"}
	if code != 200 and not parsed.has("error"):
		return {"error": "引擎响应 HTTP " + str(code)}
	return parsed

func _poll_complete(result: int, code: int, _headers_unused: PackedStringArray, body: PackedByteArray) -> void:
	poll_busy = false
	var data := _decode(result, code, body)
	if data.has("error"):
		connection_ready = false
		_connection_error(str(data.error))
	else:
		connection_ready = true
		_accept_snapshot(data)

func _action_complete(result: int, code: int, _headers_unused: PackedStringArray, body: PackedByteArray) -> void:
	action_busy = false
	var data := _decode(result, code, body)
	if data.has("error"):
		last_action_error = str(data.error)
		_connection_error(str(data.error))
		switch_after_action = false
		start_button.disabled = not connection_ready
		continue_button.disabled = not connection_ready or not bool(state.get("started", false))
		return
	last_action_error = ""
	connection_ready = true
	_accept_snapshot(data)
	if action_route in ["/start", "/configure"]:
		# Do not retain the credential in the visible control after handoff.
		key_input.text = ""
		_sync_configuration()
	if switch_after_action:
		switch_after_action = false
		_show_game()

func _accept_snapshot(data: Dictionary) -> void:
	if data.has("snapshot_sequence") and int(data.snapshot_sequence) < int(state.get("snapshot_sequence", -1)): return
	if bool(state.get("started", false)) and not bool(data.get("started", false)): return
	var incoming_epoch: String = str(data.get("epoch", ""))
	var previous_epoch: String = str(state.get("epoch", ""))
	if retired_epochs.has(incoming_epoch): return
	if incoming_epoch != previous_epoch and not previous_epoch.is_empty():
		retired_epochs[previous_epoch] = true
	# Requests may return out of order. Never roll the client back to older game state.
	if str(data.get("epoch", "")) == str(state.get("epoch", "")) and int(data.get("version", 0)) < int(state.get("version", 0)):
		return
	if str(data.get("epoch", "")) != str(state.get("epoch", "")):
		local_panel = ""
		modal_signature = ""
	state = data
	start_button.disabled = action_busy or not connection_ready
	continue_button.disabled = action_busy or not bool(state.get("started", false)) or not connection_ready
	start_button.text = "重新生成世界  →" if bool(state.get("started", false)) else "创造世界  →"
	return_button.visible = bool(state.get("started", false))
	if first_snapshot:
		first_snapshot = false
		_sync_configuration()
		if state.get("region") is Dictionary:
			setting_input.text = str(state.get("setting", setting_input.text))
	form_error.text = last_action_error if not last_action_error.is_empty() else "本机引擎已连接。" + ("找到存档，可继续旅途。" if bool(state.get("started", false)) else "")
	_render()

func _connection_error(message: String) -> void:
	if is_instance_valid(form_error): form_error.text = message
	if is_instance_valid(error_label): error_label.text = message

func _render() -> void:
	if not bool(state.get("started", false)): return
	world_view.update_world(state)
	var r: Dictionary = state.region if state.get("region") is Dictionary else {}
	var p: Dictionary = state.get("player", {})
	title_label.text = str(r.get("name", "你的世界正在形成"))
	var day: int = int(float(state.get("time", 480)) / 1440.0) + 1
	var hour: int = int(float(state.get("time", 480)) / 60.0) % 24
	var minute: int = int(state.get("time", 480)) % 60
	subtitle_label.text = "%s  ·  第 %d 天 %02d:%02d  ·  已抵达 %d 区域" % [str(state.get("title", "未写之境")), day, hour, minute, int(state.get("map_count", 0))]
	stats_label.text = "Lv.%d   %d G\nHP %d / %d   MP %d / %d" % [int(p.get("level", 1)), int(p.get("gold", 0)), int(p.get("hp", 0)), int(p.get("max_hp", 1)), int(p.get("mp", 0)), int(p.get("max_mp", 1))]
	hp_bar.max_value = float(p.get("max_hp", 1))
	hp_bar.value = float(p.get("hp", 0))
	mp_bar.max_value = float(p.get("max_mp", 1))
	mp_bar.value = float(p.get("mp", 0))
	var rules: Dictionary = {"normal": "常规法则", "no_magic": "静默领域：无法使用魔法", "healing_rain": "治愈之雨：步行 / 战斗缓慢回血", "volatile": "易燃世界：双方伤害增加", "echo": "回声：每第三回合攻击重复"}
	rule_label.text = str(rules.get(str(r.get("rule", "normal")), ""))
	var lines: Array[String] = []
	for q in state.get("quests", []):
		if str(q.region) != str(r.get("id", "")): continue
		lines.append(("✓ " if q.status == "complete" else "◇ ") + str(q.name))
	quest_label.text = "\n".join(lines) if not lines.is_empty() else "探索四周，找到正在等待你的事。"
	var d: Dictionary = state.get("director", {})
	var mode: String = str(d.get("mode", "not_configured"))
	var mode_text: String = "离线演示 · 非 LLM" if mode == "offline_demo" else "在线 · " + str(d.get("model", ""))
	if mode == "not_configured": mode_text = "尚未配置导演"
	if mode == "live_llm": mode_text += " · 思考 " + str(d.get("reasoning_effort", "low"))
	director_label.text = mode_text + "\n" + (str(d.busy) if not str(d.get("busy", "")).is_empty() else ("导演已暂停" if bool(d.get("paused", false)) else "等待重要事件 · 不按帧调用"))
	director_label.text += "\n请求 %d / %d · 已接受 %d\n输入 %d / 输出 %d tokens" % [int(d.get("calls", 0)), int(d.get("max_calls", 60)), int(d.get("accepted", 0)), int(d.get("input_tokens", 0)), int(d.get("output_tokens", 0))]
	director_label.text += "\n提前两层 · 已准备 %d / %d 区域" % [int(d.get("prefetch_ready", 0)), int(d.get("prefetch_total", 0))]
	lines.clear()
	for f in state.get("frontier", []):
		lines.append(("● " if bool(f.ready) else "○ ") + str(f.name))
	frontier_label.text = "下一片土地\n" + "\n".join(lines)
	error_label.text = last_action_error if not last_action_error.is_empty() else str(d.get("error", ""))
	pause_button.text = "继续导演" if bool(d.get("paused", false)) else "暂停导演"
	var history: Array = state.get("journal", [])
	lines.clear()
	for i in range(maxi(0, history.size() - 3), history.size()):
		lines.append(str(history[i]).left(110))
	journal_label.text = "\n\n".join(lines)
	_render_modal()

func _clear_modal() -> void:
	for child in modal_stack.get_children():
		modal_stack.remove_child(child)
		child.queue_free()
	battle_canvas = null

func _render_modal() -> void:
	var ui: Dictionary = state.get("ui", {})
	var battle: Dictionary = state.battle if state.get("battle") is Dictionary else {}
	var signature: String = JSON.stringify([ui, battle, local_panel, state.get("inventory", [])])
	if signature == modal_signature:
		return
	modal_signature = signature
	_clear_modal()
	if battle.is_empty() and ui.is_empty() and local_panel.is_empty():
		modal_overlay.hide()
		return
	modal_overlay.show()
	if not battle.is_empty():
		_label(modal_stack, str(battle.name), 24, GOLD)
		_label(modal_stack, "HP %d / %d   ·   回合 %d" % [int(battle.hp), int(battle.max_hp), int(battle.turn)], 15, MUTED)
		battle_canvas = BattleView.new()
		battle_canvas.custom_minimum_size = Vector2(510, 215)
		modal_stack.add_child(battle_canvas)
		battle_canvas.update_battle(battle)
		battle_canvas.set_visuals(state.region.get("visuals", {}), int(state.region.get("seed", 0)))
		var messages: Array[String] = []
		var log_lines: Array = battle.get("log", [])
		for i in range(maxi(0, log_lines.size() - 4), log_lines.size()): messages.append(str(log_lines[i]))
		_label(modal_stack, "\n".join(messages), 14)
		var buttons := HFlowContainer.new()
		modal_stack.add_child(buttons)
		for entry in [["1 攻击", "attack"], ["2 星火术 · 5MP", "skill"], ["3 防御", "defend"], ["4 药剂", "potion"], ["5 撤离", "flee"]]:
			var b := _button(buttons, str(entry[0]), _send_action.bind({"op": "combat", "move": entry[1]}))
			if entry[1] == "skill": b.disabled = int(state.player.mp) < 5 or state.region.rule == "no_magic"
			if entry[1] == "potion": b.disabled = int(state.player.inventory.get("potion", 0)) < 1
		return
	if not ui.is_empty():
		_label(modal_stack, str(ui.get("title", "")), 24, GOLD)
		var message_lines: Array[String] = []
		for line in ui.get("lines", []): message_lines.append(str(line))
		_label(modal_stack, "\n\n".join(message_lines), 18)
		for ch in ui.get("choices", []):
			_button(modal_stack, str(ch.text), _send_action.bind({"op": "choice", "id": ch.id}))
		if ui.get("kind") == "shop":
			for item in ui.get("goods", []):
				var b := _button(modal_stack, "%s  ·  %d G" % [str(item.name), int(item.price)], _send_action.bind({"op": "buy", "id": item.id}))
				b.disabled = int(state.player.gold) < int(item.price)
		_button(modal_stack, "继续旅途  ·  E / Esc", _send_action.bind({"op": "close"}))
		return
	if local_panel == "inventory":
		_label(modal_stack, "行囊", 25, GOLD)
		_label(modal_stack, "点击药剂使用，点击武器 / 护符装备。", 14, MUTED)
		for item in state.get("inventory", []):
			var tag: String = "已装备 · " if bool(item.equipped) else ""
			var b := _button(modal_stack, "%s%s ×%d" % [tag, str(item.name), int(item.quantity)], _send_action.bind({"op": "use", "id": item.id}))
			b.disabled = str(item.kind) == "key" or bool(item.equipped)
			_label(modal_stack, str(item.description), 13, MUTED)
	else:
		_label(modal_stack, "旅途记录", 25, GOLD)
		for line in state.get("journal", []): _label(modal_stack, str(line), 15)
		_label(modal_stack, "仍未写完的故事", 18, MINT)
		for thread in state.get("threads", []): _label(modal_stack, str(thread.title) + " · " + str(thread.note), 14, MUTED)
	_button(modal_stack, "收起  ·  Esc", func() -> void:
		local_panel = ""
		modal_signature = ""
		_render_modal()
	)

func _process(delta: float) -> void:
	poll_clock += delta
	if poll_clock >= 0.45:
		poll_clock = 0.0
		_poll()
	move_clock = maxf(0, move_clock - delta)
	if not is_instance_valid(game) or not game.visible or not connection_ready or action_busy or move_clock > 0:
		return
	if not bool(state.get("started", false)) or state.get("battle") is Dictionary or not state.get("ui", {}).is_empty() or not local_panel.is_empty():
		return
	var dx: int = 0
	var dy: int = 0
	if Input.is_physical_key_pressed(KEY_W) or Input.is_key_pressed(KEY_UP): dy = -1
	elif Input.is_physical_key_pressed(KEY_S) or Input.is_key_pressed(KEY_DOWN): dy = 1
	elif Input.is_physical_key_pressed(KEY_A) or Input.is_key_pressed(KEY_LEFT): dx = -1
	elif Input.is_physical_key_pressed(KEY_D) or Input.is_key_pressed(KEY_RIGHT): dx = 1
	if dx != 0 or dy != 0:
		move_clock = 0.14
		_send_action({"op": "move", "dx": dx, "dy": dy})

func _unhandled_key_input(event: InputEvent) -> void:
	if not event is InputEventKey or not event.pressed or event.echo or not game.visible:
		return
	var key: int = event.physical_keycode
	if key == KEY_M:
		_toggle_music()
	elif state.get("battle") is Dictionary:
		var moves: Dictionary = {KEY_1: "attack", KEY_2: "skill", KEY_3: "defend", KEY_4: "potion", KEY_5: "flee"}
		if moves.has(key): _send_action({"op": "combat", "move": moves[key]})
	elif not state.get("ui", {}).is_empty():
		if key in [KEY_E, KEY_ESCAPE, KEY_SPACE]: _send_action({"op": "close"})
	elif key == KEY_ESCAPE:
		if local_panel.is_empty():
			_show_home()
		else:
			local_panel = ""
			modal_signature = ""
			_render_modal()
	elif key == KEY_I:
		_toggle_panel("inventory")
	elif key == KEY_J:
		_toggle_panel("journal")
	elif key in [KEY_E, KEY_SPACE] and local_panel.is_empty():
		_send_action({"op": "interact"})
	get_viewport().set_input_as_handled()
