extends Control
const L = preload("res://client/i18n.gd")
## Thin Godot client: pixel world, controls and presentation. No paid model calls here.
## A single local standard-library Python helper owns state, validation and the director.

const WorldView = preload("res://client/world_view.gd")
const BattleView = preload("res://client/battle_view.gd")
const View = preload("res://client/presentation.gd")
const Icons = preload("res://client/ui_icons.gd")
const Fieldbook = preload("res://client/fieldbook.gd")
const BG := Color("111815")
const PANEL := Color("202923")
const MUTED := Color("a3ad9d")
const GOLD := Color("dcc79e")
const MINT := Color("a1b38b")

var inventory_filter: String = "all"
var selected_item: String = ""
var journal_tab: String = "active"
var item_art: Dictionary = {}
var home_pages: Array[Control] = []
var home_tabs: Array[Button] = []
var display_button: Button
var status_summary: Label
var diagnostics: VBoxContainer
var diagnostics_button: Button
var modal_scroll: ScrollContainer
var loading_overlay: CenterContainer
var loading_premise: Label
var health_label: Label
var energy_label: Label
var previous_window_mode: int = Window.MODE_WINDOWED
var atlas_panel
var mission_panel
var task_button: Button
var atlas_signature: String = ""
var journal_http: HTTPRequest
var journal_pages: Dictionary = {}
var journal_busy: bool = false
var journal_request_tab: String = ""
var journal_request_epoch: String = ""
var journal_error: String = ""
var journal_generation: int = 0
var journal_request_generation: int = 0
var redesign_dialog: ConfirmationDialog
var pending_redesign: Dictionary = {}
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
var soundscape
var music_muted: bool = false

var home: Control
var game: Control
var setting_input: TextEdit
var base_input: LineEdit
var model_input: LineEdit
var key_input: LineEdit
var mode_select: OptionButton
var hybrid_select: CheckBox
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
var role_label: Label
var world_resources: VBoxContainer
var resource_rows: Dictionary = {}
var panel_buttons: Dictionary = {}
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
var retry_failed_button: Button
var failure_list: VBoxContainer
var failure_signature: String = ""
var language_select: OptionButton
var language_http: HTTPRequest
var language_busy: bool = false
var language_sent: String = ""
var home_page_index: int = 0

func _ready() -> void:
	L.initialize()
	auto_translate_mode=Node.AUTO_TRANSLATE_MODE_DISABLED
	get_window().title="Everweave" if L.language=="en" else "Everweave · 未写之境"
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	get_window().content_scale_aspect = Window.CONTENT_SCALE_ASPECT_EXPAND
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
	journal_http = HTTPRequest.new()
	journal_http.timeout = 10
	add_child(journal_http)
	journal_http.request_completed.connect(_journal_loaded)
	language_http=HTTPRequest.new()
	language_http.timeout=4
	add_child(language_http)
	language_http.request_completed.connect(_language_saved)
	_build_game()
	_build_home()
	soundscape = preload("res://client/soundscape.gd").new()
	add_child(soundscape)
	music = soundscape.music_players[0]
	home.show()
	game.hide()
	_poll()

func _exit_tree() -> void:
	if is_instance_valid(language_http):language_http.cancel_request()
	if is_instance_valid(music):
		music.stop()
		music.stream = null
	if is_instance_valid(action_http): action_http.cancel_request()
	if is_instance_valid(poll_http): poll_http.cancel_request()
	if is_instance_valid(journal_http): journal_http.cancel_request()

func _configure_theme() -> void:
	var font := SystemFont.new()
	font.font_names = PackedStringArray(["Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans CJK SC", "WenQuanYi Zen Hei", "sans-serif"])
	var t := Theme.new()
	t.default_font = font
	t.default_font_size = 16
	t.set_color("font_color", "Label", Color("e8e4d8"))
	t.set_color("font_color", "Button", Color("e8e4d8"))
	t.set_color("font_hover_color", "Button", Color("fff2ce"))
	t.set_color("font_disabled_color", "Button", Color("6f796c"))
	t.set_stylebox("normal", "Button", _box(Color("28332b"), Color("465242"), 3))
	t.set_stylebox("hover", "Button", _box(Color("364331"), MINT, 7))
	t.set_stylebox("pressed", "Button", _box(Color("1d261f"), GOLD, 7))
	t.set_stylebox("disabled", "Button", _box(Color("1a211c"), Color("30392e"), 3))
	t.set_stylebox("normal", "LineEdit", _box(Color("141d17"), Color("424e3c"), 3))
	t.set_stylebox("focus", "LineEdit", _box(Color("1b261e"), MINT, 5))
	t.set_stylebox("normal", "TextEdit", _box(Color("141d17"), Color("424e3c"), 3))
	t.set_stylebox("focus", "TextEdit", _box(Color("1b261e"), MINT, 5))
	t.set_color("font_color", "LineEdit", Color("ede8d9"))
	t.set_color("font_color", "TextEdit", Color("ede8d9"))
	t.set_color("font_color", "CheckBox", Color("cbd6da"))
	t.set_stylebox("panel", "PanelContainer", _box(PANEL, Color("3c4738"), 3))
	t.set_color("font_color", "OptionButton", Color("e8e4d8"))
	for style in ["normal", "hover", "pressed", "disabled"]:
		t.set_stylebox(style, "OptionButton", t.get_stylebox(style,"Button"))
	t.set_stylebox("panel", "PopupMenu", _box(PANEL, Color("465242"), 3))
	t.set_constant("separation", "VBoxContainer", 12)
	t.set_constant("separation", "HBoxContainer", 10)
	theme = t

func _box(fill: Color, outline: Color, radius: int = 3) -> StyleBoxFlat:
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

func _label(parent: Node, text: String, font_size: int = 16, color: Color = Color("e8e4d8")) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", color)
	if font_size >= 24:
		var heading_font := SystemFont.new()
		heading_font.font_names = PackedStringArray(["Noto Serif CJK SC", "SimSun", "serif"])
		label.add_theme_font_override("font",heading_font)
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
	var background := preload("res://client/menu_backdrop.gd").new()
	home.add_child(background)
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var scroll := ScrollContainer.new()
	home.add_child(scroll)
	scroll.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var center := CenterContainer.new()
	center.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	center.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.add_child(center)
	var margins := _margin(center,32)
	var layout := HBoxContainer.new()
	layout.add_theme_constant_override("separation",48)
	margins.add_child(layout)
	var identity := _vbox(layout)
	identity.custom_minimum_size.x = 270
	_label(identity,"E V E R W E A V E",13,GOLD)
	_label(identity,L.t("未写之境"),48)
	_label(identity,L.t("旅途手记"),20,MUTED)
	var spacer := Control.new()
	spacer.custom_minimum_size.y = 120
	identity.add_child(spacer)
	_label(identity,L.t("写下一个地方，\n和你要扮演的人。"),22,GOLD)
	_label(identity,L.t("移动  WASD\n交互  E    行囊  I    手记  J\n全屏  F11"),13,MUTED)
	var panel := PanelContainer.new()
	panel.custom_minimum_size.x = 650
	layout.add_child(panel)
	var box := _vbox(panel)
	var language_row := HBoxContainer.new()
	box.add_child(language_row)
	_label(language_row,L.t("界面语言"),14,MUTED)
	language_select=OptionButton.new()
	language_select.add_item("简体中文",0)
	language_select.add_item("English",1)
	language_select.select(1 if L.language=="en" else 0)
	language_row.add_child(language_select)
	language_select.item_selected.connect(_change_language)
	var tabs := HBoxContainer.new()
	box.add_child(tabs)
	for entry in [[L.t("旅程"),"compass"],[L.t("显示与声音"),"screen"],[L.t("连接"),"settings"]]:
		var b := _button(tabs,entry[0],_home_tab.bind(home_tabs.size()))
		b.icon = Icons.get_icon(entry[1])
		b.add_theme_constant_override("icon_max_width",20)
		home_tabs.append(b)
	box.add_child(HSeparator.new())
	for i in range(3):
		var page := _vbox(box)
		page.custom_minimum_size = Vector2(610,400)
		home_pages.append(page)
	var journey: Control = home_pages[0]
	_label(journey,L.t("启程"),30,GOLD)
	_label(journey,L.t("地点、身份、一个悬而未决的故事。"),15,MUTED)
	setting_input = TextEdit.new()
	setting_input.custom_minimum_size = Vector2(600,164)
	setting_input.placeholder_text = L.t("描述这次旅程……")
	setting_input.text = L.t("群山间有一座建在巨树上的驿站。我是一名失去地图的信使，随身带着一封没有收件人的信。")
	setting_input.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	journey.add_child(setting_input)
	_label(journey,L.t("新旅程会在这里保存；已有进度可直接继续。"),13,MUTED)
	var buttons := HBoxContainer.new()
	journey.add_child(buttons)
	continue_button = _button(buttons,L.t("继续旅程"),_continue_world)
	start_button = _button(buttons,L.t("开始新旅程"),_start_world)
	start_button.disabled = true
	continue_button.disabled = true
	return_button = _button(journey,L.t("返回当前旅程  ·  Esc"),_show_game)
	return_button.hide()
	var display: Control = home_pages[1]
	_label(display,L.t("显示与声音"),30,GOLD)
	_label(display,L.t("窗口随屏幕比例展开，画面与文字保持原有比例。"),15,MUTED)
	display_button = _button(display,L.t("切换全屏  ·  F11"),_toggle_fullscreen)
	display_button.icon = Icons.get_icon("screen")
	display_button.add_theme_constant_override("icon_max_width",22)
	var volume := HSlider.new()
	volume.min_value = 0
	volume.max_value = 100
	volume.value = soundscape.music_gain*100 if is_instance_valid(soundscape) else 65
	display.add_child(volume)
	_label(display,L.t("音乐音量"),15,MUTED)
	volume.value_changed.connect(func(value: float) -> void:
		if is_instance_valid(soundscape): soundscape.music_gain = value / 100.0
	)
	var effects_volume := HSlider.new()
	effects_volume.min_value = 0
	effects_volume.max_value = 100
	effects_volume.value = soundscape.effects_gain*100 if is_instance_valid(soundscape) else 70
	display.add_child(effects_volume)
	_label(display,L.t("音效与环境声"),15,MUTED)
	effects_volume.value_changed.connect(func(value: float) -> void:
		if is_instance_valid(soundscape):soundscape.effects_gain = value/100.0
	)
	_button(display,L.t("开启 / 关闭音乐  ·  M"),_toggle_music)
	var connection: Control = home_pages[2]
	_label(connection,L.t("世界连接"),30,GOLD)
	_label(connection,L.t("选择内容生成服务。更改将在下次继续旅程时应用。"),14,MUTED)
	mode_select = OptionButton.new()
	mode_select.add_item("DeepSeek",0)
	mode_select.add_item(L.t("其他兼容服务"),1)
	mode_select.add_item(L.t("离线演示"),2)
	connection.add_child(mode_select)
	mode_help = _label(connection,"",13,MUTED)
	online_settings = _vbox(connection)
	hybrid_select = CheckBox.new()
	hybrid_select.text = L.t("新内容优先使用本地素材库")
	hybrid_select.button_pressed = true
	hybrid_select.tooltip_text = L.t("给模型提供匹配的图像、音频和能力候选，缺少的部分仍可原创。")
	online_settings.add_child(hybrid_select)
	provider_summary = _label(online_settings,"DeepSeek Flash",14,GOLD)
	custom_fields = GridContainer.new()
	custom_fields.columns = 2
	online_settings.add_child(custom_fields)
	_label(custom_fields,L.t("服务地址"),14,MUTED)
	base_input = LineEdit.new()
	base_input.text = "https://api.deepseek.com"
	base_input.custom_minimum_size.x = 440
	custom_fields.add_child(base_input)
	_label(custom_fields,L.t("模型"),14,MUTED)
	model_input = LineEdit.new()
	model_input.text = "deepseek-flash"
	custom_fields.add_child(model_input)
	var grid := GridContainer.new()
	grid.columns = 2
	online_settings.add_child(grid)
	_label(grid,L.t("密钥"),14,MUTED)
	key_input = LineEdit.new()
	key_input.secret = true
	key_input.custom_minimum_size.x = 440
	grid.add_child(key_input)
	_label(grid,L.t("思考等级"),14,MUTED)
	effort_select = OptionButton.new()
	grid.add_child(effort_select)
	_label(grid,L.t("请求额度"),14,MUTED)
	budget_input = SpinBox.new()
	budget_input.min_value = 1
	budget_input.max_value = 1000
	budget_input.value = 60
	grid.add_child(budget_input)
	effort_help = _label(online_settings,"",12,MUTED)
	mode_select.item_selected.connect(_mode_changed)
	_mode_changed(0)
	_button(connection,L.t("应用并继续旅程"),_continue_world)
	form_error = _label(box,L.t("连接存档中……"),13,MUTED)
	replace_dialog = ConfirmationDialog.new()
	replace_dialog.title = L.t("开始另一段旅程")
	replace_dialog.ok_button_text = L.t("开始新旅程")
	replace_dialog.cancel_button_text = L.t("保留当前旅程")
	replace_dialog.confirmed.connect(_confirm_new_world)
	replace_dialog.canceled.connect(func() -> void: pending_world_configuration = {})
	add_child(replace_dialog)
	redesign_dialog = ConfirmationDialog.new()
	redesign_dialog.title = L.t("重新创作这个地区")
	redesign_dialog.ok_button_text = L.t("重新创作")
	redesign_dialog.cancel_button_text = L.t("保留原结果")
	redesign_dialog.confirmed.connect(func() -> void:
		_post("/retry",pending_redesign)
		pending_redesign = {}
	)
	add_child(redesign_dialog)
	_home_tab(0)

func _home_tab(index: int) -> void:
	home_page_index=index
	for i in range(home_pages.size()):
		home_pages[i].visible = i == index
		home_tabs[i].modulate = Color.WHITE if i == index else Color("899582")

func _change_language(index: int, persist: bool = true, notify_backend: bool = true) -> void:
	if action_busy:
		language_select.select(1 if L.language=="en" else 0)
		return
	var value: String = "en" if index==1 else "zh"
	if value==L.language:return
	var page: int = home_page_index
	var showing_game: bool = game.visible
	var fields := {"setting":setting_input.text,"base":base_input.text,"model":model_input.text,"key":key_input.text,"mode":mode_select.selected,"effort":effort_select.get_item_metadata(effort_select.selected),"budget":budget_input.value,"hybrid":hybrid_select.button_pressed}
	var example: String = L.t("群山间有一座建在巨树上的驿站。我是一名失去地图的信使，随身带着一封没有收件人的信。")
	var keep_setting: bool = bool(state.get("started",false)) or setting_input.text!=example
	L.set_language(value,persist)
	get_window().title="Everweave" if value=="en" else "Everweave · 未写之境"
	for node in [home,game,replace_dialog,redesign_dialog]:
		remove_child(node)
		node.queue_free()
	home_tabs.clear()
	home_pages.clear()
	modal_signature=""
	failure_signature=""
	atlas_signature=""
	last_action_error=""
	_build_game()
	_build_home()
	mode_select.select(int(fields.mode))
	_mode_changed(int(fields.mode))
	_set_effort(str(fields.effort))
	if keep_setting:setting_input.text=fields.setting
	base_input.text=fields.base
	model_input.text=fields.model
	key_input.text=fields.key
	budget_input.value=fields.budget
	hybrid_select.button_pressed=fields.hybrid
	start_button.disabled=not connection_ready
	continue_button.disabled=not connection_ready or not bool(state.get("started",false))
	start_button.text=L.t("开始另一段旅程") if bool(state.get("started",false)) else L.t("开始新旅程")
	return_button.visible=bool(state.get("started",false))
	_home_tab(page)
	home.visible=not showing_game
	game.visible=showing_game
	_render()
	if notify_backend:_send_language()

func _send_language() -> void:
	if language_busy or not connection_ready:return
	language_sent=L.language
	language_busy=true
	var headers := PackedStringArray(["Content-Type: application/json","Authorization: Bearer "+session_token])
	var error: int = language_http.request(backend_url+"/language",headers,HTTPClient.METHOD_POST,JSON.stringify({"language":language_sent}))
	if error!=OK:
		language_busy=false
		form_error.text=L.t("界面语言已切换，生成语言设置暂未保存。")

func _language_saved(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	language_busy=false
	if result==HTTPRequest.RESULT_SUCCESS and code==200:
		var data: Variant = JSON.parse_string(body.get_string_from_utf8())
		if data is Dictionary:_accept_snapshot(data)
	else:form_error.text=L.t("界面语言已切换，生成语言设置暂未保存。")
	if language_sent!=L.language:_send_language()

func _toggle_fullscreen() -> void:
	var window := get_window()
	if window.mode in [Window.MODE_FULLSCREEN,Window.MODE_EXCLUSIVE_FULLSCREEN]:
		window.mode = previous_window_mode as Window.Mode
	else:
		previous_window_mode = window.mode
		window.mode = Window.MODE_FULLSCREEN
	display_button.text = L.t("退出全屏  ·  F11") if window.mode == Window.MODE_FULLSCREEN else L.t("切换全屏  ·  F11")

func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_ESCAPE and not local_panel.is_empty() and not replace_dialog.visible and not redesign_dialog.visible:
			local_panel = ""
			modal_signature = ""
			_render_modal()
			get_viewport().set_input_as_handled()
			return
		if event.keycode == KEY_F11 or (event.keycode == KEY_ENTER and event.alt_pressed):
			_toggle_fullscreen()
			get_viewport().set_input_as_handled()
		elif event.keycode == KEY_ESCAPE and home.visible and bool(state.get("started",false)) and not replace_dialog.visible:
			_show_game()
			get_viewport().set_input_as_handled()

func _inventory_category(category: String) -> void:
	inventory_filter = category
	modal_signature = ""
	_render_modal()

func _select_item(id: String) -> void:
	selected_item = id
	modal_signature = ""
	_render_modal()

func _journal_category(category: String) -> void:
	journal_tab = category
	_load_journal()
	modal_signature = ""
	_render_modal()

func _load_journal(more: bool = false) -> void:
	if journal_busy or backend_url.is_empty():return
	var page: Dictionary = journal_pages.get(journal_tab,{})
	if not more and not page.is_empty():return
	if more and page.get("next_cursor") == null:return
	journal_busy = true
	journal_error = ""
	journal_request_tab = journal_tab
	journal_request_epoch = str(state.get("epoch",""))
	journal_request_generation = journal_generation
	var url: String = backend_url + "/journal?tab=" + journal_tab
	if more: url += "&before=" + str(page.next_cursor)
	var error: Error = journal_http.request(url,PackedStringArray(["Authorization: Bearer "+session_token]))
	if error != OK:
		journal_busy = false
		journal_error = L.t("记录读取失败，可重试。")

func _journal_loaded(result: int, code: int, _headers_unused: PackedStringArray, body: PackedByteArray) -> void:
	journal_busy = false
	var data: Variant = JSON.parse_string(body.get_string_from_utf8())
	if journal_request_epoch != str(state.get("epoch","")) or journal_request_generation != journal_generation:
		if local_panel == "journal":_load_journal()
		return
	if result == HTTPRequest.RESULT_SUCCESS and code == 200 and data is Dictionary and str(data.get("epoch","")) == journal_request_epoch:
		var old: Dictionary = journal_pages.get(journal_request_tab,{"entries":[]})
		var ids: Dictionary = {}
		for entry in old.entries:ids[str(entry.id)] = true
		for entry in data.get("entries",[]):
			if not ids.has(str(entry.id)): old.entries.append(entry)
		old["next_cursor"] = data.get("next_cursor")
		journal_pages[journal_request_tab] = old
	else: journal_error = L.t("暂时无法读取旧记录，可重试。")
	if local_panel == "journal":
		if journal_request_tab != journal_tab:_load_journal()
		modal_signature = ""
		_render_modal()

func _refresh_journal() -> void:
	if journal_busy:return
	journal_generation += 1
	journal_pages.erase(journal_tab)
	_load_journal()
	modal_signature = ""
	_render_modal()

func _build_game() -> void:
	game = Control.new()
	add_child(game)
	game.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var bg := ColorRect.new()
	bg.color = BG
	game.add_child(bg)
	bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var margin := _margin(game, 16)
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var all := _vbox(margin)
	var header := HBoxContainer.new()
	all.add_child(header)
	var heading := _vbox(header)
	heading.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title_label = _label(heading, L.t("未写之境"), 27, GOLD)
	subtitle_label = _label(heading, L.t("正在织出第一片土地"), 13, MUTED)
	stats_label = _label(header, "", 16)
	stats_label.custom_minimum_size.x = 220
	stats_label.size_flags_horizontal = Control.SIZE_SHRINK_END
	for entry in [[L.t("行囊  I"),"bag","inventory"],[L.t("手记  J"),"book","journal"],[L.t("设置"),"settings","settings"]]:
		var callback: Callable = _show_home if entry[2] == "settings" else _toggle_panel.bind(entry[2])
		var b := _button(header,entry[0],callback)
		panel_buttons[entry[2]]=b
		b.icon = Icons.get_icon(entry[1])
		b.add_theme_constant_override("icon_max_width",24)
	var middle := HBoxContainer.new()
	middle.size_flags_vertical = Control.SIZE_EXPAND_FILL
	all.add_child(middle)
	var map_panel := PanelContainer.new()
	map_panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	map_panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
	middle.add_child(map_panel)
	var map_stack := Control.new()
	map_stack.custom_minimum_size = Vector2(520, 400)
	map_panel.add_child(map_stack)
	world_view = WorldView.new()
	map_stack.add_child(world_view)
	world_view.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	world_view.entity_clicked.connect(func(id: String) -> void: _send_action({"op": "interact", "id": id}))
	world_view.map_requested.connect(func() -> void: _toggle_panel("atlas"))
	task_button=_button(map_stack,"",_toggle_panel.bind("missions"))
	task_button.position=Vector2(16,16)
	task_button.size=Vector2(290,80)
	task_button.tooltip_text=L.t("行动记录 · Q")
	var task_margin: MarginContainer=_margin(task_button,12)
	task_margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	task_margin.mouse_filter=Control.MOUSE_FILTER_IGNORE
	var task_stack: VBoxContainer=_vbox(task_margin)
	task_stack.mouse_filter=Control.MOUSE_FILTER_IGNORE
	var task_caption: Label=_label(task_stack,L.t("◇  当前行动                                      Q"),11,MINT)
	task_caption.mouse_filter=Control.MOUSE_FILTER_IGNORE
	quest_label=_label(task_stack,"",14)
	quest_label.max_lines_visible=2
	quest_label.text_overrun_behavior=TextServer.OVERRUN_TRIM_ELLIPSIS
	quest_label.mouse_filter=Control.MOUSE_FILTER_IGNORE
	loading_overlay = CenterContainer.new()
	loading_overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
	map_stack.add_child(loading_overlay)
	loading_overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var loading_panel := PanelContainer.new()
	loading_panel.custom_minimum_size.x = 490
	loading_overlay.add_child(loading_panel)
	var loading_text := _vbox(loading_panel)
	_label(loading_text,L.t("第一处落脚地"),30,GOLD)
	loading_premise = _label(loading_text,"",17)
	_label(loading_text,L.t("正在准备地点、人物与画面。完成后会直接进入旅程。"),14,MUTED)
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
	modal_panel.custom_minimum_size.x = 720
	modal_center.add_child(modal_panel)
	modal_scroll = ScrollContainer.new()
	modal_scroll.custom_minimum_size = Vector2(692, 580)
	modal_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	modal_panel.add_child(modal_scroll)
	modal_stack = _vbox(modal_scroll)
	modal_stack.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	modal_stack.custom_minimum_size.x = 680
	modal_stack.minimum_size_changed.connect(func() -> void: _fit_modal.call_deferred())
	modal_overlay.hide()
	var side_panel := PanelContainer.new()
	side_panel.custom_minimum_size.x = 300
	middle.add_child(side_panel)
	var side_frame := _vbox(side_panel)
	var controls := HBoxContainer.new()
	side_frame.add_child(controls)
	pause_button = _button(controls, L.t("暂停生成"), _toggle_pause)
	retry_failed_button = _button(controls, L.t("重试"), func() -> void: _post("/retry", {}))
	var side_scroll := ScrollContainer.new()
	side_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	side_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	side_frame.add_child(side_scroll)
	var side := _vbox(side_scroll)
	side.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	side.custom_minimum_size.x = 250
	role_label=_label(side, L.t("旅人"), 14, GOLD)
	health_label = _label(side,L.t("生命"),12,MUTED)
	hp_bar = _bar(side, Color("b5856b"))
	energy_label = _label(side,L.t("魔力"),12,MUTED)
	mp_bar = _bar(side, Color("98a480"))
	world_resources=_vbox(side)
	resource_rows.clear()
	rule_label = _label(side, "", 13, MINT)
	_label(side, L.t("沿途"), 17, GOLD)
	status_summary = _label(side,"",13,MUTED)
	diagnostics_button = _button(side,L.t("生成详情  +"),_toggle_diagnostics)
	diagnostics_button.add_theme_font_size_override("font_size",12)
	diagnostics = _vbox(side)
	diagnostics.hide()
	director_label = _label(diagnostics, "", 12, MUTED)
	frontier_label = _label(side, "", 13, MUTED)
	error_label = _label(side, "", 13, Color("e7a69d"))
	failure_list = VBoxContainer.new()
	side.add_child(failure_list)
	_label(side, L.t("刚刚发生"), 17, GOLD)
	journal_label = _label(side, "", 13, MUTED)
	var footer := HBoxContainer.new()
	all.add_child(footer)
	hint_label = _label(footer, L.t("WASD  移动     E  交互     F  操作     ·  等待     G  旅图     F11  全屏                         自动保存"), 13, MUTED)
	_button(footer, "♫  M", _toggle_music)
	atlas_panel = preload("res://client/travel_atlas.gd").new()
	game.add_child(atlas_panel)
	atlas_panel.build(self)
	mission_panel=preload("res://client/mission_panel.gd").new()
	game.add_child(mission_panel)
	mission_panel.build(self)

func _toggle_diagnostics() -> void:
	diagnostics.visible = not diagnostics.visible
	diagnostics_button.text = L.t("收起详情  −") if diagnostics.visible else L.t("生成详情  +")

func _bar(parent: Node, fill: Color) -> ProgressBar:
	var bar := ProgressBar.new()
	bar.custom_minimum_size = Vector2(220, 15)
	bar.show_percentage = false
	bar.add_theme_stylebox_override("background", _box(Color("131b16"), Color("131b16"), 3))
	bar.add_theme_stylebox_override("fill", _box(fill, fill, 3))
	for kind in ["background","fill"]:
		var style: StyleBoxFlat = bar.get_theme_stylebox(kind).duplicate()
		for edge in [SIDE_LEFT,SIDE_TOP,SIDE_RIGHT,SIDE_BOTTOM]: style.set_content_margin(edge,0)
		bar.add_theme_stylebox_override(kind,style)
	parent.add_child(bar)
	return bar

func _configuration() -> Dictionary:
	var custom: bool = mode_select.selected == 1
	return {"language":L.language,"hybrid_content":hybrid_select.button_pressed,"offline": mode_select.selected == 2, "base_url": base_input.text.strip_edges() if custom else "https://api.deepseek.com", "model": model_input.text.strip_edges() if custom else "deepseek-flash", "api_key": key_input.text.strip_edges(), "deepseek_options": not custom, "reasoning_effort": str(effort_select.get_item_metadata(effort_select.selected)), "max_calls": int(budget_input.value)}

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
		var label: String = L.t("关闭思考") if effort == "none" else (L.t("服务默认（不传参数）") if effort == "default" else effort)
		effort_select.add_item(label)
		effort_select.set_item_metadata(effort_select.item_count - 1, effort)
	_set_effort(previous)
	effort_help.text = L.t("默认 low；可随时调整思考等级，应用后用于后续生成。") if index != 1 else L.t("等级由接入服务支持；不接受此参数的服务请选择“服务默认”。")
	online_settings.visible = index != 2
	custom_fields.visible = index == 1
	provider_summary.visible = index == 0
	key_input.text = ""
	mode_help.text = L.t("从一句设定开始，由模型生成世界并持续续写。") if index != 2 else L.t("仅检查地图、交互与存档功能。内容来自固定测试样例，不调用 LLM。")
	key_input.placeholder_text = L.t("留空使用此服务已有的密钥")
	if index == 0: key_input.placeholder_text = L.t("留空使用启动器加载的 DeepSeek 密钥")

func _sync_configuration() -> void:
	var cfg: Dictionary = state.get("configuration", {})
	if cfg.is_empty(): return
	base_input.text = str(cfg.get("base_url", "https://api.deepseek.com"))
	model_input.text = str(cfg.get("model", "deepseek-flash"))
	budget_input.value = int(cfg.get("max_calls", 60))
	hybrid_select.button_pressed = bool(cfg.get("hybrid_content",true))
	var index: int = 2 if bool(cfg.get("offline", false)) else (0 if base_input.text == "https://api.deepseek.com" and model_input.text == "deepseek-flash" and bool(cfg.get("deepseek_options", true)) else 1)
	mode_select.select(index)
	_mode_changed(index)
	_set_effort(str(cfg.get("reasoning_effort", "low")))

func _start_world() -> void:
	if action_busy: return
	var setting: String = setting_input.text.strip_edges()
	if setting.length() < 3 or setting.length() > 600:
		last_action_error = L.t("世界设定需要 3～600 个字符。")
		form_error.text = last_action_error
		return
	var config := _configuration()
	config["setting"] = setting
	config["replace_save"] = bool(state.get("started", false))
	if config.replace_save:
		pending_world_configuration = config
		replace_dialog.dialog_text = L.t("将按以下设定从头生成新世界：\n\n") + setting.left(180) + L.t("\n\n当前世界及进度会被替换。取消可保留原世界。")
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
	_render()

func _toggle_music() -> void:
	music_muted = not music_muted
	if is_instance_valid(soundscape):soundscape.muted = music_muted

func _toggle_pause() -> void:
	var d: Dictionary = state.get("director", {})
	if d.get("mode") == "not_configured":
		_post("/configure",_configuration())
		return
	_post("/pause", {"paused": not bool(d.get("paused", false))})

func _toggle_panel(name: String) -> void:
	if name=="inventory" and state.get("game_spec") is Dictionary and not bool(state.game_spec.systems.inventory):return
	if state.get("battle") is Dictionary or not state.get("ui", {}).is_empty(): return
	local_panel = "" if local_panel == name else name
	if is_instance_valid(soundscape):soundscape.play_ui()
	if local_panel == "journal":
		journal_generation += 1
		journal_pages.clear()
		_load_journal()
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
		_connection_error(L.t("无法请求本机引擎。请检查启动窗口。"))

func _post(route: String, body: Dictionary) -> void:
	if action_busy: return
	if backend_url.is_empty() or not connection_ready:
		_connection_error(L.t("本机引擎尚未连接。请通过启动脚本运行。"))
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
		_connection_error(L.t("动作未能发送。"))

func _send_action(body: Dictionary) -> void:
	_post("/action", body)

func _decode(result: int, code: int, body: PackedByteArray) -> Dictionary:
	if result != HTTPRequest.RESULT_SUCCESS:
		return {"error": L.t("本机连接中断；没有自动重发动作，避免重复扣款。")}
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if not parsed is Dictionary:
		return {"error": L.t("引擎返回了不可解析的响应。")}
	if code != 200 and not parsed.has("error"):
		return {"error": L.t("引擎响应 HTTP ") + str(code)}
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
		selected_item = ""
		item_art.clear()
		journal_pages.clear()
		journal_generation += 1
		journal_error = ""
	state = data
	var map_key: String = JSON.stringify([state.get("epoch"),state.get("map_count"),state.get("frontier"),state.get("quests")])
	if map_key != atlas_signature:
		atlas_signature = map_key
		if atlas_panel.visible:atlas_panel.refresh()
	start_button.disabled = action_busy or not connection_ready
	continue_button.disabled = action_busy or not bool(state.get("started", false)) or not connection_ready
	start_button.text = L.t("开始另一段旅程") if bool(state.get("started", false)) else L.t("开始新旅程")
	return_button.visible = bool(state.get("started", false))
	if first_snapshot:
		first_snapshot = false
		_sync_configuration()
		if str(state.get("configuration",{}).get("language","zh"))!=L.language:_send_language()
		if state.get("region") is Dictionary:
			setting_input.text = str(state.get("setting", setting_input.text))
	form_error.text = L.system_text(last_action_error) if not last_action_error.is_empty() else L.t("本机引擎已连接。") + (L.t("找到存档，可继续旅途。") if bool(state.get("started", false)) else "")
	_render()

func _connection_error(message: String) -> void:
	message=L.system_text(message)
	if is_instance_valid(form_error): form_error.text = message
	if is_instance_valid(error_label): error_label.text = message

func _render() -> void:
	if not bool(state.get("started", false)): return
	if is_instance_valid(soundscape):soundscape.update_state(state,game.visible)
	world_view.update_world(state)
	var r: Dictionary = state.region if state.get("region") is Dictionary else {}
	loading_overlay.visible = r.is_empty()
	loading_premise.text = str(state.get("setting",""))
	var p: Dictionary = state.get("player", {})
	title_label.text = str(r.get("name", L.t("你的世界正在形成")))
	var day: int = int(float(state.get("time", 480)) / 1440.0) + 1
	var hour: int = int(float(state.get("time", 480)) / 60.0) % 24
	var minute: int = int(state.get("time", 480)) % 60
	var world_title: String = str(state.get("title",L.t("未写之境")))
	if world_title=="未写之境 · Everweave":world_title=L.t("未写之境")
	subtitle_label.text = L.t("%s  ·  第 %d 天 %02d:%02d  ·  已抵达 %d 区域") % [world_title, day, hour, minute, int(state.get("map_count", 0))]
	stats_label.text = "Lv.%d   %d G\nHP %d / %d   MP %d / %d" % [int(p.get("level", 1)), int(p.get("gold", 0)), int(p.get("hp", 0)), int(p.get("max_hp", 1)), int(p.get("mp", 0)), int(p.get("max_mp", 1))]
	hp_bar.max_value = float(p.get("max_hp", 1))
	hp_bar.value = float(p.get("hp", 0))
	mp_bar.max_value = float(p.get("max_mp", 1))
	mp_bar.value = float(p.get("mp", 0))
	health_label.text = L.t("生命  %d / %d") % [int(p.get("hp",0)),int(p.get("max_hp",0))]
	energy_label.text = L.t("魔力  %d / %d") % [int(p.get("mp",0)),int(p.get("max_mp",0))]
	_apply_game_spec()
	var rules: Dictionary = {"normal": "", "no_magic": L.t("静默领域：无法使用魔法"), "healing_rain": L.t("治愈之雨：步行 / 战斗缓慢回血"), "volatile": L.t("易燃世界：双方伤害增加"), "echo": L.t("回声：每第三回合攻击重复")}
	rule_label.text = str(rules.get(str(r.get("rule", "normal")), ""))
	rule_label.visible = not rule_label.text.is_empty()
	var lines: Array[String] = []
	quest_label.text=L.t("留意身边的人与新的消息。")
	for q in state.get("quests",[]):
		if str(q.get("status",""))=="active":
			quest_label.text=str(q.name)
			break
	task_button.visible=not r.is_empty()
	if mission_panel.visible:mission_panel.refresh()
	status_summary.text = View.summary(state)
	var d: Dictionary = state.get("director", {})
	var mode: String = str(d.get("mode", "not_configured"))
	var mode_text: String = L.t("离线演示 · 非 LLM") if mode == "offline_demo" else L.t("在线 · ") + str(d.get("model", ""))
	if mode == "not_configured": mode_text = L.t("尚未配置导演")
	if mode == "live_llm": mode_text += L.t(" · 思考 ") + str(d.get("reasoning_effort", "low"))
	var active_lines: Array[String] = []
	for task in d.get("active_tasks", []):
		var purpose: String = L.t("世界变化") if str(task.kind) == "reaction" else (L.t("更新草案") if str(task.get("source", "")) == "refresh" else L.t("自动预生成"))
		var stage: String = L.t(" · 修复中") if str(task.get("phase", "")) == "repairing" else (L.t(" · 校验中") if str(task.get("phase", "")) == "validating" else "")
		active_lines.append(L.t("%s %s · %.0f 秒%s") % [purpose, str(task.name), float(task.get("elapsed_seconds", 0)), stage])
	var activity: String = "\n".join(active_lines) if not active_lines.is_empty() else str(d.get("busy", ""))
	director_label.text = mode_text + "\n" + (activity if not activity.is_empty() else (L.t("导演已暂停") if bool(d.get("paused", false)) else L.t("等待重要事件 · 不按帧调用")))
	var failed_tasks: Array = d.get("failed_tasks", [])
	director_label.text += L.t("\n请求 %d / %d · 其中修复 %d") % [int(d.get("calls", 0)), int(d.get("max_calls", 60)), int(d.get("repair_calls", 0))]
	director_label.text += L.t("\n已应用 %d · 过期 %d · 失败任务 %d") % [int(d.get("accepted", 0)), int(d.get("stale", 0)), failed_tasks.size()]
	director_label.text += L.t("\n在途 %d · 本地纠正 %d 处\n输入 %d / 输出 %d tokens") % [int(d.get("active_requests", 0)), int(d.get("normalization_count", 0)), int(d.get("input_tokens", 0)), int(d.get("output_tokens", 0))]
	director_label.text += L.t("\n提前两层 · 已准备 %d / %d 区域") % [int(d.get("prefetch_ready", 0)), int(d.get("prefetch_total", 0))]
	var library_usage: Dictionary = r.get("library_usage",{})
	if not library_usage.is_empty():
		director_label.text += L.t("\n图形：引用 %d · 组合 %d · 原创 %d\n地表材质 %d · 能力模块 %d") % [int(library_usage.get("referenced",0)),int(library_usage.get("composed",0)),int(library_usage.get("drawn",0)),int(library_usage.get("materials",0)),int(library_usage.get("modules",0))]
	lines.clear()
	for f in state.get("frontier", []):
		var status_text: String = L.t("可进入") if bool(f.ready) else (L.t("已暂停") if bool(d.get("paused", false)) else L.t("排队中"))
		for failure in failed_tasks:
			if str(failure.target) == str(f.id) and str(failure.kind) == "region" and not bool(f.ready): status_text = L.t("生成失败")
		for task in d.get("active_tasks", []):
			if str(task.target) == str(f.id) and str(task.kind) == "region":
				status_text = (L.t("可进入，后台更新") if bool(f.ready) else L.t("修复中") if str(task.get("phase", "")) == "repairing" else L.t("生成中")) + L.t(" · %.0f秒") % float(task.get("elapsed_seconds", 0))
		lines.append(("● " if bool(f.ready) else "○ ") + str(f.name) + " · " + status_text)
	frontier_label.text = L.t("下一片土地\n") + "\n".join(lines)
	error_label.text = last_action_error if not last_action_error.is_empty() else (str(d.get("error", "")) if failed_tasks.is_empty() else "")
	var library_error: String = preload("res://client/asset_library.gd").last_error
	if not library_error.is_empty():error_label.text = library_error
	retry_failed_button.disabled = failed_tasks.is_empty()
	_render_failures(failed_tasks)
	pause_button.text = L.t("继续生成") if bool(d.get("paused", false)) else L.t("暂停生成")
	var history: Array = state.get("journal", [])
	lines.clear()
	for i in range(maxi(0, history.size() - 1), history.size()):
		lines.append(str(history[i]).left(110))
	journal_label.text = "\n\n".join(lines)
	_render_modal()

func _render_failures(tasks: Array) -> void:
	var signature: String = JSON.stringify(tasks)
	if signature == failure_signature: return
	failure_signature = signature
	for child in failure_list.get_children():
		failure_list.remove_child(child)
		child.queue_free()
	var categories: Dictionary = {"format":L.t("格式"), "reference":L.t("身份与引用"), "gameplay":L.t("玩法与地图"), "provider":L.t("模型服务"), "internal":L.t("引擎处理")}
	for task in tasks:
		var row := VBoxContainer.new()
		failure_list.add_child(row)
		var kind: String = L.t("地区生成") if str(task.kind) == "region" else L.t("世界变化")
		_label(row, L.t("%s · %s失败") % [str(task.name), kind], 14, Color("e7a69d"))
		var details: Array = task.get("issues", [])
		var reason: String = str(task.get("message", L.t("生成未完成")))
		if not details.is_empty():
			var field_path: String = str(details[0].get("path", "$"))
			reason = (field_path + "\n" if field_path != "$" else "") + str(details[0].get("message", reason))
			if details.size() > 1: reason += L.t("\n另有 %d 项问题，重试时一并修复。") % (details.size() - 1)
		var friendly: Dictionary = {"format":L.t("部分内容需要调整。"), "reference":L.t("物品或人物信息还需核对。"), "gameplay":L.t("道路或交互需要修复。"), "provider":L.t("生成服务暂时没有完成请求。")}
		var detail_label := _label(row, str(friendly.get(str(task.get("category","format")),L.t("内容准备未完成。"))), 12, MUTED)
		detail_label.tooltip_text = reason + "\n" + JSON.stringify(details, "  ")
		if str(task.kind) == "region":
			_button(row,L.t("放弃候选，重新创作"),_offer_redesign.bind(str(task.target),str(task.name)))
		_button(row, L.t("重试此任务"), _post.bind("/retry", {"target":str(task.target), "kind":str(task.kind)}))

func _offer_redesign(target: String, name: String) -> void:
	pending_redesign = {"target":target,"kind":"region","mode":"redesign"}
	redesign_dialog.dialog_text = L.t("舍弃「") + name + L.t("」上次失败的候选内容，按同一目的地重新创作。已有地图不会被删除，新请求仍计入额度。")
	redesign_dialog.popup_centered(Vector2i(540,220))

func _clear_modal() -> void:
	for child in modal_stack.get_children():
		modal_stack.remove_child(child)
		child.queue_free()
	battle_canvas = null

func _fit_modal() -> void:
	if not is_instance_valid(modal_scroll) or not is_instance_valid(world_view): return
	var available_height: float = maxf(160,world_view.size.y - 48)
	modal_scroll.custom_minimum_size.y = clampf(modal_stack.get_combined_minimum_size().y + 8,100,minf(610,available_height))

func _render_modal() -> void:
	if local_panel=="missions" and state.get("ui",{}).is_empty() and not state.get("battle") is Dictionary:
		modal_overlay.hide()
		atlas_panel.hide()
		mission_panel.show()
		mission_panel.refresh()
		return
	mission_panel.hide()
	var ui: Dictionary = state.get("ui", {})
	var battle: Dictionary = state.battle if state.get("battle") is Dictionary else {}
	if local_panel == "atlas" and ui.is_empty() and battle.is_empty():
		modal_overlay.hide()
		if not atlas_panel.visible:atlas_panel.open()
		return
	atlas_panel.hide()
	var waiting_phase: String = _exit_wait_phase(ui)
	var signature: String = JSON.stringify([ui, battle, local_panel, state.get("inventory", []), state.get("available_actions", []), waiting_phase, inventory_filter, selected_item, journal_tab, state.get("quests", []), state.get("threads", []), state.get("journal", [])])
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
		_label(modal_stack, L.t("HP %d / %d   ·   回合 %d") % [int(battle.hp), int(battle.max_hp), int(battle.turn)], 15, MUTED)
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
		var generated_actions: Array = state.get("available_actions", [])
		if bool(battle.get("authored", false)):
			for index in range(generated_actions.size()):
				var entry: Dictionary = generated_actions[index]
				var b := _button(buttons, str(index + 1) + " " + str(entry.label), _send_action.bind({"op":"combat","move":"rule:"+str(entry.id)}))
				b.disabled = not bool(entry.enabled)
				b.tooltip_text = str(entry.description)
				if b.disabled: _label(modal_stack, str(entry.label) + "：" + L.system_text(str(entry.get("blocked_reason", entry.description))), 13, MUTED)
			_button(buttons, L.t("撤離 · Esc"), _send_action.bind({"op":"combat","move":"flee"}))
			return
		for entry in [[L.t("1 攻击"), "attack"], [L.t("2 星火术 · 5MP"), "skill"], [L.t("3 防御"), "defend"], [L.t("4 药剂"), "potion"], [L.t("5 撤离"), "flee"]]:
			var b := _button(buttons, str(entry[0]), _send_action.bind({"op": "combat", "move": entry[1]}))
			if entry[1] == "skill": b.disabled = int(state.player.mp) < 5 or state.region.rule == "no_magic"
			if entry[1] == "potion": b.disabled = int(state.player.inventory.get("potion", 0)) < 1
		return
	if not ui.is_empty():
		if ui.get("kind") == "pending_exit":
			_label(modal_stack, L.t("可以进入下一地区了") if waiting_phase == "ready" else L.t("正在准备 ") + str(ui.get("name", L.t("下一地区"))), 24, GOLD)
			var explanation: String = L.t("地图由后台自动提前准备，无需反复触发出口。你也可以先回去探索。")
			if waiting_phase == "failed": explanation = L.t("这个地区的生成未通过校验，可重试此任务；其他地区会继续准备。")
			elif waiting_phase == "paused": explanation = L.t("后台已暂停追加请求，可在右侧继续导演。")
			elif waiting_phase == "ready": explanation = L.t("地图已准备好，按 E 或点击下方按钮即可进入。")
			_label(modal_stack, explanation, 18)
			if waiting_phase == "ready": _button(modal_stack, L.t("进入 ") + str(ui.get("name", L.t("下一地区"))) + " · E", _send_action.bind({"op":"enter_exit"}))
			elif waiting_phase == "failed": _button(modal_stack, L.t("重试这个地区"), _post.bind("/retry", {"target":str(ui.target),"kind":"region"}))
			_button(modal_stack, L.t("继续探索当前地区 · Esc"), _send_action.bind({"op":"close"}))
			return
		var modal_title: String = str(ui.get("title",""))
		_label(modal_stack,L.t(modal_title) if ui.get("system_title",false) else modal_title,24,GOLD)
		if not ui.get("portraits",[]).is_empty():
			var portraits := HFlowContainer.new()
			modal_stack.add_child(portraits)
			for portrait in ui.portraits:
				var row := HBoxContainer.new()
				row.custom_minimum_size=Vector2(180,72)
				portraits.add_child(row)
				var face := TextureRect.new()
				face.texture=Fieldbook.item_texture(self,{"icon_visual":portrait.visual})
				face.custom_minimum_size=Vector2(56,64)
				face.expand_mode=TextureRect.EXPAND_IGNORE_SIZE
				face.stretch_mode=TextureRect.STRETCH_KEEP_ASPECT_CENTERED
				face.texture_filter=CanvasItem.TEXTURE_FILTER_NEAREST
				row.add_child(face)
				var name_label: Label = _label(row,str(portrait.name),15,GOLD)
				name_label.autowrap_mode=TextServer.AUTOWRAP_OFF
		var message_lines: Array[String] = []
		for line in ui.get("lines", []): message_lines.append(str(line))
		_label(modal_stack, "\n\n".join(message_lines), 18)
		if ui.get("kind") == "actions" and ui.get("actions", []).is_empty():
			_label(modal_stack, L.t("这里暂时没有可用的自定义操作。走近人物或物件后按 E 交互，或继续探索其他位置。"), 16, MUTED)
		for entry in ui.get("actions", []):
			var b := _button(modal_stack, str(entry.label), _send_action.bind({"op":"content_action","id":entry.id}))
			b.disabled = not bool(entry.enabled)
			b.tooltip_text = str(entry.description)
			if b.disabled: _label(modal_stack, L.system_text(str(entry.get("blocked_reason", entry.description))), 14, MUTED)
		for ch in ui.get("choices", []):
			_button(modal_stack, str(ch.text), _send_action.bind({"op": "choice", "id": ch.id}))
		if ui.get("kind") == "shop":
			for item in ui.get("goods", []):
				var b := _button(modal_stack, "%s  ·  %d G" % [str(item.name), int(item.price)], _send_action.bind({"op": "buy", "id": item.id}))
				b.disabled = int(state.player.gold) < int(item.price)
		_button(modal_stack, L.t("返回  ·  E / Esc"), _send_action.bind({"op": "close"}))
		return
	if local_panel == "inventory":
		Fieldbook.inventory(self,modal_stack)
	else:
		Fieldbook.journal(self,modal_stack)
	_button(modal_stack, L.t("收起  ·  Esc"), func() -> void:
		local_panel = ""
		modal_signature = ""
		_render_modal()
	)

func _exit_wait_phase(ui: Dictionary) -> String:
	if ui.get("kind") != "pending_exit": return ""
	if bool(ui.get("ready", false)): return "ready"
	var director: Dictionary = state.get("director", {})
	for task in director.get("failed_tasks", []):
		if str(task.kind) == "region" and str(task.target) == str(ui.get("target", "")): return "failed"
	for task in director.get("active_tasks", []):
		if str(task.kind) == "region" and str(task.target) == str(ui.get("target", "")): return "generating"
	return "paused" if bool(director.get("paused", false)) else "queued"

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
	if Input.is_physical_key_pressed(KEY_W) or Input.is_key_pressed(KEY_W) or Input.is_key_pressed(KEY_UP): dy = -1
	elif Input.is_physical_key_pressed(KEY_S) or Input.is_key_pressed(KEY_S) or Input.is_key_pressed(KEY_DOWN): dy = 1
	elif Input.is_physical_key_pressed(KEY_A) or Input.is_key_pressed(KEY_A) or Input.is_key_pressed(KEY_LEFT): dx = -1
	elif Input.is_physical_key_pressed(KEY_D) or Input.is_key_pressed(KEY_D) or Input.is_key_pressed(KEY_RIGHT): dx = 1
	if dx != 0 or dy != 0:
		move_clock = 0.14
		_send_action({"op": "move", "dx": dx, "dy": dy})

func _unhandled_key_input(event: InputEvent) -> void:
	if not event is InputEventKey or not event.pressed or event.echo or not game.visible:
		return
	# Windows accessibility input can supply a valid logical key with an unrelated
	# scan code. Hotkeys follow the logical key; physical-only input still works.
	var key: int = event.keycode if event.keycode != 0 else event.physical_keycode
	if not local_panel.is_empty() and key != KEY_M:
		if key == KEY_I: _toggle_panel("inventory")
		elif key == KEY_J: _toggle_panel("journal")
		elif key == KEY_G: _toggle_panel("atlas")
		elif key == KEY_Q: _toggle_panel("missions")
		elif key == KEY_ESCAPE:
			local_panel = ""
			modal_signature = ""
			_render_modal()
		get_viewport().set_input_as_handled()
		return
	if key == KEY_M:
		_toggle_music()
	elif state.get("battle") is Dictionary:
		var authored: Array = state.get("available_actions", [])
		if bool(state.battle.get("authored", false)):
			var index: int = key - KEY_1
			if index >= 0 and index < mini(9, authored.size()):
				_send_action({"op":"combat","move":"rule:"+str(authored[index].id)})
			elif key == KEY_ESCAPE: _send_action({"op":"combat","move":"flee"})
			get_viewport().set_input_as_handled()
			return
		var moves: Dictionary = {KEY_1: "attack", KEY_2: "skill", KEY_3: "defend", KEY_4: "potion", KEY_5: "flee"}
		if moves.has(key): _send_action({"op": "combat", "move": moves[key]})
	elif not state.get("ui", {}).is_empty():
		if key in [KEY_E, KEY_SPACE] and _exit_wait_phase(state.ui) == "ready": _send_action({"op":"enter_exit"})
		elif key in [KEY_E, KEY_ESCAPE, KEY_SPACE]: _send_action({"op": "close"})
	elif key == KEY_ESCAPE:
		if local_panel.is_empty():
			_show_home()
		else:
			local_panel = ""
			modal_signature = ""
			_render_modal()
	elif key == KEY_F:
		_send_action({"op":"actions"})
	elif key == KEY_PERIOD:
		_send_action({"op":"wait"})
	elif key == KEY_I:
		_toggle_panel("inventory")
	elif key == KEY_J:
		_toggle_panel("journal")
	elif key == KEY_G:
		_toggle_panel("atlas")
	elif key == KEY_Q:
		_toggle_panel("missions")
	elif key in [KEY_W, KEY_A, KEY_S, KEY_D, KEY_UP, KEY_LEFT, KEY_DOWN, KEY_RIGHT] and local_panel.is_empty():
		# Handle the first tap as an event: a down/up pair can arrive within one
		# frame and disappear before _process polls held keys.
		if connection_ready and not action_busy and move_clock <= 0:
			var dx: int = 1 if key in [KEY_D, KEY_RIGHT] else -1 if key in [KEY_A, KEY_LEFT] else 0
			var dy: int = 1 if key in [KEY_S, KEY_DOWN] else -1 if key in [KEY_W, KEY_UP] else 0
			move_clock = 0.14
			_send_action({"op":"move","dx":dx,"dy":dy})
	elif key in [KEY_E, KEY_SPACE] and local_panel.is_empty():
		_send_action({"op": "interact"})
	get_viewport().set_input_as_handled()

func _apply_game_spec() -> void:
	var value: Variant = state.get("game_spec")
	var custom: bool = value is Dictionary
	health_label.visible=not custom
	energy_label.visible=not custom
	hp_bar.visible=not custom
	mp_bar.visible=not custom
	world_resources.visible=custom
	role_label.text=str(value.identity) if custom else L.t("旅人")
	panel_buttons.inventory.visible=not custom or bool(value.systems.inventory)
	panel_buttons.inventory.text=(str(value.inventory_label)+"  I") if custom else L.t("行囊  I")
	panel_buttons.journal.text=(str(value.journal_label)+"  J") if custom else L.t("手记  J")
	if not custom:return
	for row in resource_rows.values():row.box.hide()
	var summary: Array[String] = []
	for resource in value.resources:
		var key: String = str(resource.id)
		if not resource_rows.has(key):
			var box := _vbox(world_resources)
			resource_rows[key]={"box":box,"label":_label(box,"",12,MUTED),"bar":_bar(box,Color("98a480"))}
		var row: Dictionary = resource_rows[key]
		row.box.show()
		row.label.text="%s  %s / %s" % [str(resource.label),_resource_number(resource.value),_resource_number(resource.max)]
		row.bar.max_value=float(resource.max)
		row.bar.value=float(resource.value)
		row.bar.visible=str(resource.display)=="bar"
		summary.append("%s %s" % [str(resource.label),_resource_number(resource.value)])
	stats_label.text=" · ".join(summary.slice(0,2))
	if bool(value.systems.progression):stats_label.text="Lv.%d  " % int(state.player.level)+stats_label.text

func _resource_number(value: Variant) -> String:
	return str(int(value)) if is_equal_approx(float(value),roundf(float(value))) else String.num(float(value),1)
