extends RefCounted
const L = preload("res://client/i18n.gd")
const View = preload("res://client/presentation.gd")
const Icons = preload("res://client/ui_icons.gd")
const Compiler = preload("res://client/visual_compiler.gd")

static func item_texture(main, item: Dictionary) -> Texture2D:
	var recipe: Variant = item.get("icon_visual")
	if recipe is Dictionary and recipe.get("size") is Array and recipe.size.size() == 2 and (recipe.get("layers") is Array or recipe.has("asset") or recipe.has("parts")):
		var signature: String = JSON.stringify(recipe)
		if not main.item_art.has(signature): main.item_art[signature] = Compiler.compile_sprite(recipe, {})
		return main.item_art[signature]
	return Icons.get_icon(str(item.get("kind", "tool")))

static func header(main, parent: Node, title: String, detail: String) -> void:
	main._label(parent, title, 28, main.GOLD)
	main._label(parent, detail, 13, main.MUTED)
	parent.add_child(HSeparator.new())

static func inventory(main, parent: Node) -> void:
	var spec: Variant = main.state.get("game_spec")
	header(main,parent,str(spec.inventory_label) if spec is Dictionary else L.t("行囊"),str(View.inventory(main.state).size()) if spec is Dictionary else L.t("%d 种随身物品   /   %d 金币") % [View.inventory(main.state).size(),int(main.state.get("player",{}).get("gold",0))])
	var filters := HFlowContainer.new()
	parent.add_child(filters)
	for entry in [["all",L.t("全部")],["consumable",L.t("补给")],["weapon",L.t("武器")],["charm",L.t("饰物")],["key",L.t("要物")],["tool",L.t("工具")]]:
		if spec is Dictionary and not bool(spec.systems.equipment) and entry[0] in ["weapon","charm"]:continue
		var b: Button = main._button(filters,entry[1],main._inventory_category.bind(entry[0]))
		b.modulate = Color.WHITE if main.inventory_filter == entry[0] else Color("999e92")
	var content := HBoxContainer.new()
	content.add_theme_constant_override("separation",24)
	parent.add_child(content)
	var grid := GridContainer.new()
	grid.columns = 3
	grid.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	content.add_child(grid)
	var items: Array[Dictionary] = View.inventory(main.state,main.inventory_filter)
	if items.is_empty():
		main._label(parent,L.t("这一栏还没有物品。"),16,main.MUTED)
		return
	var selected: Dictionary = items[0]
	for item in items:
		if item.id == main.selected_item: selected = item
	for item in items:
		var tile := Button.new()
		tile.custom_minimum_size = Vector2(96,112)
		tile.focus_mode = Control.FOCUS_NONE
		tile.tooltip_text = str(item.get("name",L.t("物品")))
		tile.pressed.connect(main._select_item.bind(item.id))
		if item.id == selected.id: tile.add_theme_stylebox_override("normal",main._box(Color("30382b"),main.GOLD,3))
		grid.add_child(tile)
		var margin: MarginContainer = main._margin(tile,7)
		margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		margin.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var column: VBoxContainer = main._vbox(margin)
		column.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var icon := TextureRect.new()
		icon.texture = item_texture(main,item)
		icon.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		icon.custom_minimum_size = Vector2(64,48)
		icon.mouse_filter = Control.MOUSE_FILTER_IGNORE
		column.add_child(icon)
		var name_label: Label = main._label(column,str(item.get("name",L.t("物品"))),12)
		name_label.max_lines_visible = 1
		name_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		name_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		var quantity: Label = main._label(column,L.t("已装备") if bool(item.get("equipped",false)) else "× %d" % int(item.quantity),11,main.GOLD)
		quantity.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	var detail: VBoxContainer = main._vbox(content)
	detail.custom_minimum_size.x = 270
	main._label(detail,str(selected.type_label),12,main.MUTED)
	main._label(detail,str(selected.get("name",L.t("物品"))),24,main.GOLD)
	main._label(detail,str(selected.get("description","")),16)
	var use: Dictionary = selected.get("use",{}) if selected.get("use") is Dictionary else {}
	if use.is_empty():
		var effects: Dictionary = {"heal":L.t("恢复生命"), "restore_mp":L.t("恢复魔力"), "attack":L.t("攻击"), "defense":L.t("防御"), "burn":L.t("灼烧"), "drain":L.t("汲取")}
		if selected.kind in ["weapon","charm","consumable"]:
			main._label(detail,"%s  +%d" % [str(effects.get(selected.get("effect",""),L.t("效力"))),int(selected.get("power",0))],14,main.GOLD)
	main._label(detail,L.t("携带数量  %d") % int(selected.quantity),13,main.MUTED)
	if bool(selected.get("equipped",false)):
		main._label(detail,L.t("正在装备"),15,main.GOLD)
	elif bool(selected.can_use):
		var action: Button = main._button(detail,str(selected.action_label),main._send_action.bind({"op":"use","id":selected.id}))
		action.disabled = not bool(selected.get("enabled",true))
		if action.disabled: main._label(detail,str(selected.get("blocked_reason",L.t("当前不可使用。"))),14,main.MUTED)
	else: main._label(detail,L.t("随身保管。在相关人物或物件处使用。"),14,main.MUTED)

static func journal(main, parent: Node) -> void:
	var spec: Variant = main.state.get("game_spec")
	header(main,parent,str(spec.journal_label) if spec is Dictionary else L.t("旅途手记"),L.t("记下未完的事，也记下已经发生的事。"))
	var tabs := HBoxContainer.new()
	parent.add_child(tabs)
	for entry in [["active",L.t("待办")],["threads",L.t("线索")],["history",L.t("经历")],["complete",L.t("已完成")]]:
		var b: Button = main._button(tabs,entry[1],main._journal_category.bind(entry[0]))
		b.modulate = Color.WHITE if main.journal_tab == entry[0] else Color("999e92")
	main._button(tabs,L.t("刷新"),main._refresh_journal)
	var entries: Array = []
	if main.journal_tab == "history":
		for line in View.history(main.state): entries.append({"name":"", "description":line})
	elif main.journal_tab == "threads":
		for thread in View.records(main.state.get("threads",[])):
			entries.append({"name":thread.get("title",L.t("线索")),"description":thread.get("note","")})
	else:
		for q in View.objectives(main.state,"all"):
			if (main.journal_tab == "active" and str(q.get("status","active")) == "active") or (main.journal_tab == "complete" and str(q.get("status","active")) != "active"):
				entries.append(q)
	if main.journal_pages.has(main.journal_tab):entries = main.journal_pages[main.journal_tab].entries
	if main.journal_busy:main._label(parent,L.t("正在翻阅记录……"),13,main.MUTED)
	if not main.journal_error.is_empty():main._label(parent,main.journal_error,13,main.MUTED)
	if entries.is_empty() and not main.journal_busy: main._label(parent,L.t("暂无记录。继续探索，新的经历会留在这里。"),16,main.MUTED)
	for entry in entries:
		var row := PanelContainer.new()
		row.add_theme_stylebox_override("panel",main._box(Color("202923"),Color("394235"),2))
		parent.add_child(row)
		var column: VBoxContainer = main._vbox(row)
		var name: String = str(entry.get("name",""))
		if not name.is_empty():
			main._label(column,(L.t("已结束 · ") if entry.get("status") == "failed" else "") + name,18,main.GOLD)
		main._label(column,View.prose(entry),16)
		if entry.has("region"):
			var current: Dictionary = main.state.get("region",{}) if main.state.get("region") is Dictionary else {}
			main._label(column,L.t("当前地区") if entry.region == current.get("id") else L.t("旅途中的其他地区"),12,main.MUTED)
	var page: Dictionary = main.journal_pages.get(main.journal_tab,{})
	if page.get("next_cursor") != null:
		var more: Button = main._button(parent,L.t("翻阅更早的记录"),main._load_journal.bind(true))
		more.disabled = main.journal_busy
