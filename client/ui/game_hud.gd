extends Control
## Presentation composition. main owns authoritative snapshots and network actions.
const L = preload("res://client/i18n.gd")
const Icons = preload("res://client/ui_icons.gd")
const Pixel = preload("res://assets/fonts/FusionPixel.ttf")
var main
var journey_drawer
var developer_overlay
var pause_menu
var sound_button: Button
var status_button: Button
var tutorial: Label
var title_region: String = ""
var arrival_until: int = 0
var tutorial_until: int = 0
var ready_count: int = -1
var ready_notice_until: int = 0

func icon_button(parent: Node, icon: String, tip: String, callback: Callable) -> Button:
	var button: Button = main._button(parent, "", callback)
	button.icon = Icons.get_icon(icon)
	button.custom_minimum_size = Vector2(42,42)
	button.expand_icon = true
	button.add_theme_constant_override("icon_max_width",24)
	button.add_theme_stylebox_override("normal",StyleBoxEmpty.new())
	button.tooltip_text = tip
	button.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	return button

func build(controller) -> void:
	main = controller
	var background := ColorRect.new()
	background.color = Color("111b1c")
	background.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(background)
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var margin: MarginContainer = main._margin(self, 20)
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var stack: VBoxContainer = main._vbox(margin)
	stack.add_theme_constant_override("separation",8)
	var header := HBoxContainer.new()
	stack.add_child(header)
	var titles: VBoxContainer = main._vbox(header)
	titles.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	titles.add_theme_constant_override("separation",0)
	main.title_label = main._label(titles,L.t("未写之境"),24,main.GOLD)
	main.title_label.add_theme_font_override("font",Pixel)
	main.title_label.max_lines_visible = 1
	main.title_label.autowrap_mode = TextServer.AUTOWRAP_OFF
	main.title_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	main.subtitle_label = main._label(titles,"",14,main.MUTED)
	main.stats_label = main._label(header,"",18,main.GOLD)
	main.stats_label.size_flags_horizontal = Control.SIZE_SHRINK_END
	main.stats_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	main.stats_label.custom_minimum_size.x = 300
	main.stats_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	var map_stack := Control.new()
	map_stack.size_flags_vertical = Control.SIZE_EXPAND_FILL
	stack.add_child(map_stack)
	main.world_view = preload("res://client/world_view.gd").new()
	map_stack.add_child(main.world_view)
	main.world_view.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	main.world_view.entity_clicked.connect(func(id: String) -> void: main._send_action({"op":"interact","id":id}))
	main.world_view.map_requested.connect(func() -> void: main._toggle_panel("atlas"))
	main.task_button = main._button(map_stack, "", main._toggle_panel.bind("missions"))
	main.task_button.position = Vector2(16,16)
	main.task_button.size = Vector2(420,52)
	main.task_button.tooltip_text = L.t("行动记录 · Q")
	var task_margin: MarginContainer = main._margin(main.task_button,8)
	task_margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	task_margin.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var task_row := HBoxContainer.new()
	task_row.mouse_filter = Control.MOUSE_FILTER_IGNORE
	task_margin.add_child(task_row)
	var marker: Label = main._label(task_row,"Q",24,main.MINT)
	marker.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	marker.custom_minimum_size.x = 28
	marker.autowrap_mode = TextServer.AUTOWRAP_OFF
	marker.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	marker.add_theme_font_override("font",Pixel)
	marker.mouse_filter = Control.MOUSE_FILTER_IGNORE
	main.quest_label = main._label(task_row,"",18)
	main.quest_label.max_lines_visible = 1
	main.quest_label.autowrap_mode = TextServer.AUTOWRAP_OFF
	main.quest_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	main.quest_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	main.quest_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	main.loading_overlay = CenterContainer.new()
	main.loading_overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
	map_stack.add_child(main.loading_overlay)
	main.loading_overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var loading_panel := PanelContainer.new()
	loading_panel.custom_minimum_size.x = 490
	main.loading_overlay.add_child(loading_panel)
	var loading_text: VBoxContainer = main._vbox(loading_panel)
	main._label(loading_text,L.t("第一处落脚地"),30,main.GOLD)
	main.loading_premise = main._label(loading_text,"",18)
	main._label(loading_text,L.t("正在准备地点、人物与画面。完成后会直接进入旅程。"),16,main.MUTED)
	var footer := HBoxContainer.new()
	stack.add_child(footer)
	for entry in [["bag","inventory","行囊  I"],["book","journal","手记  J"]]:
		main.panel_buttons[entry[1]] = icon_button(footer,entry[0],L.t(entry[2]),main._toggle_panel.bind(entry[1]))
	icon_button(footer,"compass",L.t("旅途 · Tab"),main._toggle_aux.bind("journey"))
	main.hint_label = main._label(footer,"",16,main.MUTED)
	main.hint_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	main.hint_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	main.hint_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	status_button = main._button(footer,"",main._toggle_aux.bind("journey"))
	status_button.add_theme_font_override("font",preload("res://assets/fonts/LXGWWenKaiScreen.ttf"))
	status_button.add_theme_font_size_override("font_size",16)
	status_button.add_theme_stylebox_override("normal",StyleBoxEmpty.new())
	sound_button = icon_button(footer,"sound_on","",main._toggle_music)
	sound_button.toggle_mode = true
	main.panel_buttons.settings = icon_button(footer,"settings",L.t("菜单 · Esc"),main._toggle_aux.bind("pause"))

	main.modal_overlay = Control.new()
	map_stack.add_child(main.modal_overlay)
	main.modal_overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	main.modal_overlay.mouse_filter = Control.MOUSE_FILTER_STOP
	var dim := ColorRect.new()
	dim.color = Color(0.025,0.04,0.08,.66)
	main.modal_overlay.add_child(dim)
	dim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var center := CenterContainer.new()
	main.modal_overlay.add_child(center)
	center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var modal_panel := PanelContainer.new()
	modal_panel.custom_minimum_size.x = 720
	center.add_child(modal_panel)
	main.modal_scroll = ScrollContainer.new()
	main.modal_scroll.custom_minimum_size = Vector2(692,580)
	main.modal_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	modal_panel.add_child(main.modal_scroll)
	main.modal_stack = main._vbox(main.modal_scroll)
	main.modal_stack.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	main.modal_stack.custom_minimum_size.x = 680
	main.modal_stack.minimum_size_changed.connect(func() -> void: main._fit_modal.call_deferred())
	main.modal_overlay.hide()
	main.atlas_panel = preload("res://client/travel_atlas.gd").new()
	add_child(main.atlas_panel)
	main.atlas_panel.build(main)
	main.mission_panel = preload("res://client/mission_panel.gd").new()
	add_child(main.mission_panel)
	main.mission_panel.build(main)

	journey_drawer = preload("res://client/ui/journey_drawer.tscn").instantiate()
	add_child(journey_drawer)
	journey_drawer.heading(L.t("旅途"))
	journey_drawer.closed.connect(func() -> void: main._toggle_aux("journey"))
	var side: VBoxContainer = journey_drawer.body
	main.role_label = main._label(side,L.t("旅人"),24,main.GOLD)
	main.health_label = main._label(side,L.t("生命"),16,main.MUTED)
	main.hp_bar = main._bar(side,Color("b5856b"))
	main.energy_label = main._label(side,L.t("魔力"),16,main.MUTED)
	main.mp_bar = main._bar(side,Color("98a480"))
	main.world_resources = main._vbox(side)
	main.resource_rows.clear()
	main.rule_label = main._label(side,"",16,main.MINT)
	main.status_summary = main._label(side,"",18,main.GOLD)
	main.frontier_label = main._label(side,"",18,main.MUTED)
	main._label(side,L.t("刚刚发生"),24,main.GOLD)
	main.journal_label = main._label(side,"",18,main.MUTED)
	main._button(side,L.t("行动记录 · Q"),main._toggle_panel.bind("missions"))
	main._button(side,L.t("旅图 · G"),main._toggle_panel.bind("atlas"))
	journey_drawer.hide()

	developer_overlay = preload("res://client/ui/developer_overlay.tscn").instantiate()
	add_child(developer_overlay)
	developer_overlay.heading(L.t("开发诊断 · Ctrl+D"))
	main.diagnostics = developer_overlay.body
	main.director_label = main._label(main.diagnostics,"",16,main.MUTED)
	main.error_label = main._label(main.diagnostics,"",16,Color("e7a69d"))
	var controls := HBoxContainer.new()
	main.diagnostics.add_child(controls)
	main.pause_button = main._button(controls,L.t("暂停生成"),main._toggle_pause)
	main.retry_failed_button = main._button(controls,L.t("重试"),func() -> void: main._post("/retry",{}))
	main.failure_list = VBoxContainer.new()
	main.diagnostics.add_child(main.failure_list)
	developer_overlay.closed.connect(func() -> void: main._toggle_aux("diagnostics"))
	developer_overlay.hide()

	pause_menu = preload("res://client/ui/pause_menu.tscn").instantiate()
	add_child(pause_menu)
	pause_menu.heading(L.t("旅途菜单"))
	pause_menu.closed.connect(func() -> void: main._toggle_aux("pause"))
	main._button(pause_menu.body,L.t("返回旅程"),main._toggle_aux.bind("pause"))
	main._button(pause_menu.body,L.t("显示与声音"),func() -> void: main._show_home();main._home_tab(1))
	main._button(pause_menu.body,L.t("旅途 · Tab"),main._toggle_aux.bind("journey"))
	main.diagnostics_button = main._button(pause_menu.body,L.t("开发诊断 · Ctrl+D"),main._toggle_diagnostics)
	main._button(pause_menu.body,L.t("世界连接"),func() -> void: main._show_home();main._home_tab(2))
	main._label(pause_menu.body,L.t("移动 WASD · 交互 E · 操作 F\n行囊 I · 手记 J · 旅图 G · 目标 Q\n等待 . · 静音 M · 全屏 Alt+Enter"),16,main.MUTED)
	pause_menu.hide()
	AudioPrefs.changed.connect(sync_audio)
	sync_audio()

func sync_audio() -> void:
	sound_button.set_pressed_no_signal(not AudioPrefs.master_muted)
	sound_button.icon = Icons.get_icon("sound_off" if AudioPrefs.master_muted else "sound_on")
	sound_button.tooltip_text = L.t("声音已关闭 · 按 M 恢复") if AudioPrefs.master_muted else L.t("声音开启 · 按 M 静音")

func show_aux(name: String) -> void:
	journey_drawer.visible = name == "journey"
	developer_overlay.visible = name == "diagnostics"
	pause_menu.visible = name == "pause"

func update(snapshot: Dictionary) -> void:
	var region: Dictionary = snapshot.get("region",{}) if snapshot.get("region") is Dictionary else {}
	var now := Time.get_ticks_msec()
	if str(region.get("id","")) != title_region:
		title_region = str(region.get("id",""))
		arrival_until = now + 4500
		tutorial_until = now + 10000
	main.title_label.add_theme_font_size_override("font_size",36 if now < arrival_until else 24)
	var d: Dictionary = snapshot.get("director",{})
	var failed: bool = not d.get("failed_tasks",[]).is_empty()
	var ready: int = int(snapshot.get("map_count",0))
	if ready_count >= 0 and ready > ready_count: ready_notice_until = now + 6000
	ready_count = ready
	status_button.text = L.t("生成暂时失败 · 查看") if failed else L.t("新地区已经准备好") if now < ready_notice_until else L.t("远方正在编织…") if int(d.get("active_requests",0)) > 0 else ""
	status_button.icon = Icons.get_icon("warning" if failed else "generation") if not status_button.text.is_empty() else null
	status_button.tooltip_text = L.t("旅途 · Tab")
	main.hint_label.text = ""
	if main.local_panel.is_empty() and snapshot.get("ui",{}).is_empty() and snapshot.get("battle") == null:
		if not AudioPrefs.learned.has("move") and now < tutorial_until:
			main.hint_label.text = L.t("WASD · 出发探索")
		else:
			var available: Array = snapshot.get("available_actions",[])
			if available.any(func(a: Dictionary) -> bool: return a.get("target","") == "player" and a.get("enabled",false)):
				main.hint_label.text = L.t("F · 当前可用操作")
