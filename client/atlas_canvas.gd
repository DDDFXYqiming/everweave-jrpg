extends Control
const L = preload("res://client/i18n.gd")
## Stable diagram of known roads. Positions and route marks are local UI state.
signal place_selected(id: String)
var data: Dictionary = {}
var nodes: Dictionary = {}
var positions: Dictionary = {}
var children: Dictionary = {}
var collapsed: Dictionary = {}
var concealed: Dictionary = {}
var textures: Dictionary = {}
var route: Array[String] = []
var selected: String = ""
var pan := Vector2.ZERO
var zoom: float = .85
var dragging: bool = false
var drag_origin := Vector2.ZERO
var drag_distance: float = 0
var preferences: String = ""
var view_ready: bool = false
var marked_target: String = ""
const CARD := Vector2(220,100)

func _ready() -> void:
	clip_contents = true
	mouse_filter = Control.MOUSE_FILTER_STOP
	custom_minimum_size = Vector2(480,350)
	resized.connect(queue_redraw)

func set_graph(value: Dictionary) -> void:
	var fresh: bool = str(value.get("epoch","")) != str(data.get("epoch",""))
	data = value
	if fresh:
		view_ready = false
		marked_target = ""
		pan = Vector2.ZERO
		zoom = .85
		selected = ""
		positions.clear()
		collapsed.clear()
		textures.clear()
		route.clear()
		preferences = "user://atlas-" + str(data.get("epoch","")).sha256_text() + ".cfg"
		var cfg := ConfigFile.new()
		if cfg.load(preferences) == OK:
			positions = cfg.get_value("view","positions",{})
			collapsed = cfg.get_value("view","collapsed",{})
			pan = cfg.get_value("view","pan",size * .5)
			zoom = clampf(float(cfg.get_value("view","zoom",.85)),.3,1.7)
			selected = str(cfg.get_value("view","selected",""))
			marked_target = str(cfg.get_value("view","target",""))
			view_ready = bool(cfg.get_value("view","ready",not positions.is_empty()))
	nodes.clear()
	children.clear()
	for n in data.get("nodes",[]):
		nodes[str(n.id)] = n
		var parent: String = str(n.get("parent",""))
		if not children.has(parent): children[parent] = []
		children[parent].append(str(n.id))
	for id in nodes:
		if positions.has(id) and positions[id] is Vector2: continue
		var parent: String = str(nodes[id].get("parent",""))
		var origin: Vector2 = positions.get(parent,Vector2(-270,0)) + Vector2(270,0)
		var candidate := origin
		var attempt: int = 0
		while positions.values().has(candidate):
			attempt += 1
			candidate = origin + Vector2(0,150 * ceili(attempt / 2.0) * (1 if attempt % 2 else -1))
		positions[id] = candidate
	if nodes.size() > 80 and fresh:
		for id in nodes:
			var descendants: Array[String] = descend(id)
			if descendants.size() > 5 and not str(data.current) in descendants and id != data.current:
				if path_to(id).size() > 4: collapsed[id] = true
	_reveal_selected()
	if not view_ready: locate_current()
	queue_redraw()
	save_view()

func save_view() -> void:
	if preferences.is_empty(): return
	var cfg := ConfigFile.new()
	cfg.set_value("view","positions",positions)
	cfg.set_value("view","collapsed",collapsed)
	cfg.set_value("view","pan",pan)
	cfg.set_value("view","zoom",zoom)
	cfg.set_value("view","selected",selected)
	cfg.set_value("view","target",marked_target)
	cfg.set_value("view","ready",view_ready)
	cfg.save(preferences)

func descend(id: String) -> Array[String]:
	var result: Array[String] = []
	var queue: Array = children.get(id,[]).duplicate()
	var seen: Dictionary = {id:true}
	while not queue.is_empty():
		var next: String = str(queue.pop_front())
		if seen.has(next): continue
		seen[next] = true
		result.append(next)
		queue.append_array(children.get(next,[]))
	return result

func path_to(target: String) -> Array[String]:
	var current: String = str(data.get("current",""))
	var parents: Dictionary = {current:""}
	var queue: Array[String] = [current]
	while not queue.is_empty():
		var id: String = queue.pop_front()
		if id == target: break
		for edge in data.get("edges",[]):
			var next: String = str(edge.b) if str(edge.a) == id else str(edge.a) if str(edge.b) == id else ""
			if not next.is_empty() and not parents.has(next):
				parents[next] = id
				queue.append(next)
	var result: Array[String] = []
	if not parents.has(target): return result
	var cursor: String = target
	while not cursor.is_empty():
		result.push_front(cursor)
		cursor = str(parents[cursor])
	return result

func _reveal_selected() -> void:
	for id in collapsed.keys():
		var below: Array[String] = descend(id)
		if str(data.get("current","")) in below or selected in below:
			collapsed.erase(id)
		for step in route:
			if step in below: collapsed.erase(id)
	concealed.clear()
	for id in collapsed:
		for next in descend(id): concealed[next] = true

func select_place(id: String, center: bool = false) -> void:
	if not nodes.has(id): return
	selected = id
	_reveal_selected()
	if center: pan = size * .5 - positions[id] * zoom
	place_selected.emit(id)
	queue_redraw()
	save_view()

func toggle_branch() -> void:
	if selected.is_empty(): return
	if collapsed.has(selected): collapsed.erase(selected)
	else: collapsed[selected] = true
	_reveal_selected()
	queue_redraw()
	save_view()

func locate_current() -> void:
	if nodes.has(str(data.get("current",""))):view_ready = true
	select_place(str(data.get("current","")),true)

func change_zoom(factor: float, anchor: Vector2 = Vector2.INF) -> void:
	if anchor == Vector2.INF: anchor = size * .5
	var point: Vector2 = (anchor - pan) / zoom
	zoom = clampf(zoom * factor,.3,1.7)
	pan = anchor - point * zoom
	queue_redraw()
	save_view()

func _texture(id: String, thumbnail: Dictionary) -> Texture2D:
	if textures.has(id): return textures[id]
	var rows: Array = thumbnail.pixels
	var img := Image.create(rows[0].size(),rows.size(),false,Image.FORMAT_RGBA8)
	for y in range(rows.size()):
		for x in range(rows[y].size()): img.set_pixel(x,y,Color(str(thumbnail.colors[int(rows[y][x])])))
	textures[id] = ImageTexture.create_from_image(img)
	return textures[id]

func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO,size),Color("151f19"))
	if nodes.is_empty():
		draw_string(get_theme_default_font(),Vector2(24,48),L.t("到访第一处地点后，旅图会从这里展开。"),HORIZONTAL_ALIGNMENT_LEFT,-1,16,Color("b4bda8"))
		return
	draw_set_transform(pan,0,Vector2(zoom,zoom))
	for edge in data.get("edges",[]):
		var a: String = str(edge.a)
		var b: String = str(edge.b)
		if concealed.has(a) or concealed.has(b) or not positions.has(a) or not positions.has(b): continue
		var ink := Color("6e7c60")
		if a in route and b in route and absi(route.find(a)-route.find(b)) == 1: ink = Color("e6c78b")
		if bool(nodes[a].visited) and bool(nodes[b].visited): draw_line(positions[a],positions[b],ink,2,true)
		else: draw_dashed_line(positions[a],positions[b],ink,2,9,true)
	var font: Font = get_theme_default_font()
	for id in nodes:
		if concealed.has(id): continue
		var center: Vector2 = positions[id]
		var rect := Rect2(center - CARD*.5,CARD)
		if not Rect2(Vector2.ZERO,size).intersects(Rect2(rect.position*zoom+pan,rect.size*zoom)): continue
		var node: Dictionary = nodes[id]
		var visited: bool = bool(node.visited)
		draw_style_box(_style(Color("293729") if visited else Color("1b271f"),Color("e1c28c") if id == selected else Color("536249")),rect)
		if node.get("thumbnail") is Dictionary:
			draw_texture_rect(_texture(id,node.thumbnail),Rect2(rect.position+Vector2(12,27),Vector2(54,36)),false)
		else: draw_string(font,rect.position+Vector2(30,60),"?",HORIZONTAL_ALIGNMENT_LEFT,-1,25,Color("8f9a7e"))
		var title: String = str(node.name)
		draw_string(font,rect.position+Vector2(77,31),title.left(9),HORIZONTAL_ALIGNMENT_LEFT,136,14,Color("e6d9bb"))
		if title.length()>9: draw_string(font,rect.position+Vector2(77,52),title.substr(9,8)+("…" if title.length()>17 else ""),HORIZONTAL_ALIGNMENT_LEFT,136,14,Color("e6d9bb"))
		var status: String = L.t("你在这里") if id == str(data.current) else L.t("已到访") if visited else L.t("尚未到访")
		if collapsed.has(id): status += L.t("  +%d处") % descend(id).size()
		draw_string(font,rect.position+Vector2(77,81),status,HORIZONTAL_ALIGNMENT_LEFT,140,12,Color("b9ba98"))
		if not node.get("tasks",[]).is_empty(): draw_rect(Rect2(rect.end-Vector2(14,96),Vector2(5,15)),Color("d1b477"))
		if id == str(data.current):draw_circle(center-Vector2(0,59),5,Color("ebd193"))
	draw_set_transform(Vector2.ZERO)

func _style(fill: Color, border: Color) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = fill
	style.border_color = border
	style.set_border_width_all(1)
	style.set_corner_radius_all(4)
	return style

func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		if event.pressed and event.button_index in [MOUSE_BUTTON_WHEEL_UP,MOUSE_BUTTON_WHEEL_DOWN]:
			change_zoom(1.15 if event.button_index == MOUSE_BUTTON_WHEEL_UP else 1/1.15,event.position)
			accept_event()
		elif event.button_index == MOUSE_BUTTON_LEFT:
			if event.pressed:
				dragging = true
				drag_origin = event.position
				drag_distance = 0
			else:
				if dragging and drag_distance < 5:
					var point: Vector2 = (event.position-pan)/zoom
					for id in nodes:
						if not concealed.has(id) and Rect2(positions[id]-CARD*.5,CARD).has_point(point):
							select_place(id)
							break
				dragging = false
				save_view()
			accept_event()
	elif event is InputEventMouseMotion and dragging:
		pan += event.relative
		drag_distance += event.relative.length()
		queue_redraw()
		accept_event()
