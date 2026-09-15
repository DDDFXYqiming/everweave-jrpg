extends PanelContainer
const L = preload("res://client/i18n.gd")
var main
var rows: VBoxContainer
var detail: VBoxContainer
var completed := false
var selected := ""
var signature := ""

func build(owner) -> void:
	main=owner
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var margin: MarginContainer=main._margin(self,28)
	var stack: VBoxContainer=main._vbox(margin)
	var header := HBoxContainer.new()
	stack.add_child(header)
	main._label(header,L.t("行动记录"),28,main.GOLD).size_flags_horizontal=Control.SIZE_EXPAND_FILL
	main._button(header,L.t("收起 · Q / Esc"),func() -> void:main._toggle_panel("missions"))
	var tabs := HBoxContainer.new()
	stack.add_child(tabs)
	main._button(tabs,L.t("进行中"),func() -> void:completed=false;selected="";refresh(true))
	main._button(tabs,L.t("已完成"),func() -> void:completed=true;selected="";refresh(true))
	main._button(tabs,L.t("完整记录 · J"),func() -> void:main._toggle_panel("journal"))
	stack.add_child(HSeparator.new())
	var body := HBoxContainer.new()
	body.add_theme_constant_override("separation",30)
	body.size_flags_vertical=Control.SIZE_EXPAND_FILL
	stack.add_child(body)
	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size.x=310
	scroll.horizontal_scroll_mode=ScrollContainer.SCROLL_MODE_DISABLED
	body.add_child(scroll)
	rows=main._vbox(scroll)
	rows.size_flags_horizontal=Control.SIZE_EXPAND_FILL
	var details_scroll := ScrollContainer.new()
	details_scroll.size_flags_horizontal=Control.SIZE_EXPAND_FILL
	details_scroll.horizontal_scroll_mode=ScrollContainer.SCROLL_MODE_DISABLED
	body.add_child(details_scroll)
	detail=main._vbox(details_scroll)
	detail.size_flags_horizontal=Control.SIZE_EXPAND_FILL
	main._label(stack,L.t("记录已得知的线索与选择。新的目标会随旅程出现。"),13,main.MUTED)
	hide()

func refresh(force := false) -> void:
	var next: String=JSON.stringify([main.state.get("quests",[]),completed,selected])
	if not force and next==signature:return
	signature=next
	for parent in [rows,detail]:
		for child in parent.get_children():parent.remove_child(child);child.queue_free()
	var shown: Array=[]
	for q in main.state.get("quests",[]):
		if (str(q.get("status","active"))!="active")==completed:shown.append(q)
	if shown.is_empty():
		main._label(detail,L.t("还没有完成的记录。") if completed else L.t("留意身边的人与新的消息。"),20,main.MUTED)
		return
	var chosen: Dictionary=shown[0]
	for q in shown:
		if str(q.id)==selected:chosen=q
	for q in shown:
		var key: String=str(q.id)
		var button: Button=main._button(rows,("✓  " if q.status=="complete" else "·  ")+str(q.name),func() -> void:selected=key;refresh(true))
		button.custom_minimum_size=Vector2(300,56)
		button.text_overrun_behavior=TextServer.OVERRUN_TRIM_ELLIPSIS
		if key==str(chosen.id):button.add_theme_stylebox_override("normal",main._box(Color("303d38"),main.GOLD,4))
	main._label(detail,L.t("已完成") if chosen.status=="complete" else L.t("当前行动"),13,main.MINT)
	main._label(detail,str(chosen.name),28,main.GOLD)
	detail.add_child(HSeparator.new())
	main._label(detail,str(chosen.get("description","")),19)
	for previous in main.state.get("quests",[]):
		if previous.id in chosen.get("depends",[]):
			main._label(detail,"✓  "+str(previous.name),14,main.MUTED)
