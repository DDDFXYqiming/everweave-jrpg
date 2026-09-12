extends PanelContainer
const L = preload("res://client/i18n.gd")
const Canvas = preload("res://client/atlas_canvas.gd")
var main
var canvas
var details: VBoxContainer
var message: Label
var route_label: Label
var matches: HFlowContainer
var request: HTTPRequest
var busy: bool = false
var again: bool = false
var request_epoch: String = ""
var route_target: String = ""
var search_input: LineEdit

func build(owner) -> void:
	main = owner
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	offset_left = 0
	offset_top = 0
	offset_right = 0
	offset_bottom = 0
	var stack: VBoxContainer = main._vbox(self)
	var top := HBoxContainer.new()
	stack.add_child(top)
	main._label(top,L.t("旅途地图"),28,main.GOLD)
	main._button(top,L.t("定位我"),func() -> void: canvas.locate_current())
	main._button(top,"−",func() -> void: canvas.change_zoom(1/1.2))
	main._button(top,"+",func() -> void: canvas.change_zoom(1.2))
	main._button(top,L.t("刷新"),refresh)
	main._button(top,L.t("收起 · Esc"),func() -> void: main._toggle_panel("atlas"))
	var search := LineEdit.new()
	search_input = search
	search.placeholder_text = L.t("寻找一个去过或听说过的地方……")
	stack.add_child(search)
	search.text_changed.connect(_search)
	matches = HFlowContainer.new()
	stack.add_child(matches)
	var body := HBoxContainer.new()
	body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	stack.add_child(body)
	canvas = Canvas.new()
	canvas.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	canvas.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body.add_child(canvas)
	canvas.place_selected.connect(_select)
	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size.x = 300
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	body.add_child(scroll)
	details = VBoxContainer.new()
	details.custom_minimum_size.x = 275
	details.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(details)
	message = main._label(stack,L.t("拖动画布 · 滚轮缩放 · 连线表示已知道路，并非地理比例"),12,main.MUTED)
	route_label = main._label(stack,L.t("点击一个地点，查看记录或标记路线。"),15,main.GOLD)
	request = HTTPRequest.new()
	request.timeout = 10
	add_child(request)
	request.request_completed.connect(_loaded)
	hide()

func open() -> void:
	if str(canvas.data.get("epoch","")) != str(main.state.get("epoch","")):
		canvas.set_graph({"epoch":str(main.state.get("epoch","")),"current":"","nodes":[],"edges":[]})
		route_target = ""
		route_label.text = L.t("点击一个地点，查看记录或标记路线。")
		search_input.text = ""
		for child in details.get_children():
			details.remove_child(child)
			child.queue_free()
	show()
	refresh()

func refresh() -> void:
	if busy:
		again = true
		return
	if main.backend_url.is_empty():return
	busy = true
	request_epoch = str(main.state.get("epoch",""))
	message.text = L.t("正在翻开旅图……")
	var error: Error = request.request(main.backend_url+"/atlas",PackedStringArray(["Authorization: Bearer "+main.session_token]))
	if error != OK:
		busy = false
		message.text = L.t("旅图读取失败，可点击刷新。")

func _loaded(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	busy = false
	var value: Variant = JSON.parse_string(body.get_string_from_utf8())
	if result == HTTPRequest.RESULT_SUCCESS and code == 200 and value is Dictionary and str(value.get("epoch","")) == str(main.state.get("epoch","")) and request_epoch == str(main.state.get("epoch","")):
		canvas.set_graph(value)
		if not canvas.view_ready: canvas.locate_current()
		elif canvas.selected.is_empty() or not canvas.nodes.has(canvas.selected): canvas.select_place(str(value.current))
		else: _select(canvas.selected)
		if route_target.is_empty():route_target = canvas.marked_target
		if canvas.nodes.has(route_target):_mark(route_target)
		message.text = L.t("拖动画布 · 滚轮缩放 · 实线已到访 / 虚线未到访 · 连线不是地理比例")
	else: message.text = L.t("旅图暂时无法读取。原有旅程未改变，可点击刷新。")
	if again:
		again = false
		refresh()

func _select(id: String) -> void:
	for child in details.get_children():
		details.remove_child(child)
		child.queue_free()
	if not canvas.nodes.has(id): return
	var node: Dictionary = canvas.nodes[id]
	main._label(details,str(node.name),24,main.GOLD)
	main._label(details,L.t("你在这里") if id == str(canvas.data.current) else L.t("已到访") if bool(node.visited) else L.t("尚未到访"),13,main.MUTED)
	main._label(details,str(node.description),16)
	if not bool(node.ready):main._label(details,L.t("这个地区尚未准备完成。已发现的道路仍保留在旅图中。"),14,main.MUTED)
	var tasks: Array = node.get("tasks",[])
	if not tasks.is_empty():
		main._label(details,L.t("未完的事"),17,main.GOLD)
		for task in tasks:
			main._label(details,str(task.name),15)
			main._label(details,str(task.get("description","")),13,main.MUTED)
	main._label(details,L.t("已知道路"),17,main.GOLD)
	for edge in canvas.data.get("edges",[]):
		var other: String = str(edge.b) if str(edge.a) == id else str(edge.a) if str(edge.b) == id else ""
		if not other.is_empty():main._button(details,str(canvas.nodes[other].name),canvas.select_place.bind(other,true))
	main._button(details,L.t("标记到这里的路线"),_mark.bind(id))
	if not canvas.children.get(id,[]).is_empty():
		main._button(details,L.t("展开这一带") if canvas.collapsed.has(id) else L.t("收起后方支路"),func() -> void:
			canvas.toggle_branch()
			_select(id)
		)

func _mark(id: String) -> void:
	canvas.route = canvas.path_to(id)
	route_target = id
	canvas.marked_target = id
	canvas._reveal_selected()
	canvas.queue_redraw()
	canvas.save_view()
	if canvas.route.size() < 2: route_label.text = L.t("你已经在这里。") if id == str(canvas.data.current) else L.t("尚未发现连接这两个地点的道路。")
	else:
		var next: String = str(canvas.nodes[canvas.route[1]].name)
		route_label.text = L.t("经过 %d 个地区；先寻找当前区域通往「%s」的出口。沿途机关需照常解决。") % [canvas.route.size()-1,next]

func _search(text: String) -> void:
	for child in matches.get_children():
		matches.remove_child(child)
		child.queue_free()
	if text.strip_edges().is_empty():return
	var count: int = 0
	for id in canvas.nodes:
		if str(canvas.nodes[id].name).to_lower().contains(text.to_lower()):
			main._button(matches,str(canvas.nodes[id].name),canvas.select_place.bind(str(id),true))
			count += 1
			if count >= 6:break
	if count == 0:main._label(matches,L.t("没有找到已知地点。"),13,main.MUTED)

func _exit_tree() -> void:
	if is_instance_valid(request):request.cancel_request()
