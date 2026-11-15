extends Node2D

const Walking = preload("res://client/walking.gd")
const Lighting = preload("res://client/world/lighting.gd")
const TILE: float = 16.0
const STEP_SECONDS: float = 0.14

var sprite_for: Callable
var recipe_for: Callable
var atmosphere: Dictionary = {}
var actors: Dictionary = {}
var player: Node2D
var player_body: Sprite2D
var player_cell := Vector2.ZERO
var player_facing := Vector2i(0, 1)
var player_tween: Tween
var step_until: float = 0.0
var elapsed: float = 0.0
var shadow_texture: Texture2D
var ground: Node2D
var marks: Node2D
var region: Dictionary = {}
var ready_targets: Dictionary = {}
var walk_goal := Vector2i(-1, -1)
var has_visuals: bool = false

func _ready() -> void:
	y_sort_enabled = true
	shadow_texture = _ellipse()
	ground = Node2D.new()
	ground.material = CanvasItemMaterial.new()
	ground.material.light_mode = CanvasItemMaterial.LIGHT_MODE_UNSHADED
	ground.draw.connect(_draw_ground)
	add_child(ground)
	marks = Node2D.new()
	marks.z_index = 20
	marks.material = CanvasItemMaterial.new()
	marks.material.light_mode = CanvasItemMaterial.LIGHT_MODE_UNSHADED
	marks.draw.connect(_draw_marks)
	add_child(marks)

func _ellipse() -> Texture2D:
	var image := Image.create(14, 5, false, Image.FORMAT_RGBA8)
	for y in range(5):
		for x in range(14):
			var d: float = pow((x + 0.5 - 7.0) / 7.0, 2) + pow((y + 0.5 - 2.5) / 2.5, 2)
			image.set_pixel(x, y, Color(0, 0, 0, 0.32 if d <= 1.0 else 0.0))
	return ImageTexture.create_from_image(image)

func foot(cell: Vector2, footprint: Array = [1, 1]) -> Vector2:
	return (cell + Vector2(float(footprint[0]) * 0.5, 1.0)) * TILE

func _make(key: String, footprint: Array, label: String = "") -> Node2D:
	var node := Node2D.new()
	var shadow := Sprite2D.new()
	shadow.name = "Shadow"
	shadow.texture = shadow_texture
	shadow.scale = Vector2(maxf(1.0, float(footprint[0])), 1.0)
	shadow.position = Vector2(0, -1)
	node.add_child(shadow)
	var body := Sprite2D.new()
	body.name = "Body"
	body.centered = false
	node.add_child(body)
	node.set_meta("key", "")
	add_child(node)
	_skin(node, key, label)
	return node

func _skin(node: Node2D, key: String, label: String = "") -> void:
	if str(node.get_meta("key")) == key: return
	node.set_meta("key", key)
	var body: Sprite2D = node.get_node("Body")
	body.texture = sprite_for.call(key, elapsed)
	body.offset = Vector2(-floorf(body.texture.get_width() / 2.0), -body.texture.get_height())
	if node.has_node("Glow"): node.get_node("Glow").free()
	var light: PointLight2D = Lighting.for_sprite(key + " " + label, recipe_for.call(key), body.texture, atmosphere)
	if light != null:
		light.name = "Glow"
		node.add_child(light)

func sync(data: Dictionary, regenerate: bool) -> void:
	var incoming: Dictionary = data.get("region", {})
	var changed_region: bool = str(incoming.get("id", "")) != str(region.get("id", ""))
	region = incoming
	ready_targets.clear()
	for item in data.get("frontier", []): ready_targets[str(item.id)] = bool(item.ready)
	if regenerate or changed_region:
		for id in actors: actors[id].queue_free()
		actors.clear()
		if player != null: player.queue_free()
		player = null
	var seen: Dictionary = {}
	var index: int = 0
	for prop in region.get("props", []):
		index += 1
		var id: String = "prop:" + str(prop.get("id", index))
		if bool(prop.get("spent", false)): continue
		_place(id, str(prop.get("sprite", prop.kind)), Vector2(float(prop.x), float(prop.y)), prop.get("footprint", [1, 1]), prop, "prop")
		seen[id] = true
	for entity in region.get("entities", []):
		var kind: String = str(entity.kind)
		if bool(entity.get("spent", false)) and kind != "chest": continue
		var key: String = kind
		if kind == "npc": key = "npc_%d_0" % int(entity.get("appearance", 0))
		elif kind == "enemy": key = str(entity.get("monster", "slime"))
		elif kind == "exit": key = "portal" if ready_targets.get(str(entity.get("target", "")), true) else "portal_pending"
		elif kind == "chest" and bool(entity.get("spent", false)): key = "chest_open"
		if entity.has("sprite") and has_visuals: key = str(entity.sprite)
		var id: String = "entity:" + str(entity.id)
		_place(id, key, Vector2(float(entity.x), float(entity.y)), entity.get("footprint", [1, 1]), entity, kind)
		seen[id] = true
	for id in actors.keys():
		if not seen.has(id):
			actors[id].queue_free()
			actors.erase(id)
	_sync_player(data.get("player", {}), changed_region or regenerate)

func _place(id: String, key: String, cell: Vector2, footprint: Array, source: Dictionary, kind: String) -> void:
	var target: Vector2 = foot(cell, footprint)
	var label: String = "" if kind in ["npc", "enemy"] else str(source.get("name", "")) + " " + str(source.get("id", "")) + " " + str(source.get("kind", ""))
	var node: Node2D = actors.get(id)
	if node == null:
		node = _make(key, footprint, label)
		node.position = target
		actors[id] = node
	else:
		_skin(node, key, label)
		if node.position.distance_to(target) > 0.5:
			if node.position.distance_to(target) > TILE * 1.6:
				node.position = target
			else:
				var body: Sprite2D = node.get_node("Body")
				if absf(target.x - node.position.x) > 0.5: body.flip_h = target.x < node.position.x
				var tween: Tween = node.create_tween()
				tween.tween_property(node, "position", target, STEP_SECONDS * 1.6)
				node.set_meta("moving_until", elapsed + STEP_SECONDS * 1.6)
	node.set_meta("kind", kind)
	node.set_meta("source", source)
	node.set_meta("cell", cell)
	node.set_meta("footprint", footprint)
	var body: Sprite2D = node.get_node("Body")
	body.modulate = Color(0.55, 0.55, 0.55, 0.75) if kind == "chest" and bool(source.get("spent", false)) else Color.WHITE

func _sync_player(p: Dictionary, snap: bool) -> void:
	var cell := Vector2(float(p.get("x", 0)), float(p.get("y", 0)))
	var facing: Array = p.get("facing", [0, 1])
	if player == null:
		player = _make("hero_0", [1, 1])
		player.name = "Player"
		player_body = player.get_node("Body")
		var lantern: PointLight2D = Lighting.lantern(atmosphere)
		if lantern != null: player.add_child(lantern)
		snap = true
	if snap or cell.distance_to(player_cell) > 1.5:
		if player_tween != null: player_tween.kill()
		player.position = foot(cell)
	elif cell != player_cell:
		if player_tween != null: player_tween.kill()
		player_tween = player.create_tween()
		player_tween.tween_property(player, "position", foot(cell), STEP_SECONDS)
		step_until = elapsed + STEP_SECONDS + 0.05
	player_cell = cell
	player_facing = Vector2i(int(facing[0]), int(facing[1]))
	if player_facing.x != 0: player_body.flip_h = player_facing.x < 0

func player_point() -> Vector2:
	return player.position if player != null else Vector2.ZERO

func _process(delta: float) -> void:
	elapsed += delta
	if player != null:
		var walking: bool = elapsed < step_until
		var phase: int = int(elapsed * 10.0) % 2
		player_body.position = Vector2(0, -1 if walking and phase == 1 else 0)
		player_body.scale = Vector2(1.0, 1.0)
		if walking: player_body.scale = Vector2(1.06, 0.94) if phase == 0 else Vector2(0.96, 1.04)
		elif player_facing.y < 0: player_body.scale = Vector2(1.0, 0.97)
	for id in actors:
		var node: Node2D = actors[id]
		var key: String = str(node.get_meta("key"))
		var body: Sprite2D = node.get_node("Body")
		body.texture = sprite_for.call(key, elapsed)
		if float(node.get_meta("moving_until", 0.0)) > elapsed:
			body.position.y = -1 if int(elapsed * 9.0) % 2 == 1 else 0
		else:
			body.position.y = 0
	ground.queue_redraw()
	marks.queue_redraw()

func _draw_ground() -> void:
	for id in actors:
		var node: Node2D = actors[id]
		var kind: String = str(node.get_meta("kind"))
		var source: Dictionary = node.get_meta("source")
		if kind in ["exit", "shrine"]:
			var accent: Color = atmosphere.get("accent", Color(0.4, 0.85, 0.8))
			ground.draw_circle(node.position - Vector2(0, 4), 9.0 + sin(elapsed * 2.0), Color(accent, 0.16))
		elif kind == "enemy":
			ground.draw_arc(node.position - Vector2(0, 2), 8.0, 0, TAU, 18, Color(0.91, 0.42, 0.42, 0.7), 1.0)
			var footprint: Array = node.get_meta("footprint")
			if int(footprint[0]) > 1 or int(footprint[1]) > 1:
				var rect: Rect2i = Walking.rect_from_bottom_left({"x": source.x, "y": source.y, "footprint": footprint})
				ground.draw_rect(Rect2(Vector2(rect.position) * TILE, Vector2(rect.size) * TILE), Color(0.91, 0.42, 0.42, 0.35), false, 1.0)
	if walk_goal.x >= 0:
		var alpha: float = 0.55 + 0.3 * sin(elapsed * 6.0)
		var at := Vector2(walk_goal) * TILE
		for corner in [Vector2(1, 1), Vector2(11, 1), Vector2(1, 11), Vector2(11, 11)]:
			ground.draw_rect(Rect2(at + corner, Vector2(4, 4)), Color(0.96, 0.86, 0.6, alpha), false, 1.0)

func _bang(at: Vector2, ink: Color) -> void:
	marks.draw_rect(Rect2(at + Vector2(-2, -8), Vector2(4, 9)), Color(0.08, 0.06, 0.05))
	marks.draw_rect(Rect2(at + Vector2(-1, -7), Vector2(2, 4)), ink)
	marks.draw_rect(Rect2(at + Vector2(-1, -2), Vector2(2, 2)), ink)

func _draw_marks() -> void:
	for id in actors:
		var node: Node2D = actors[id]
		var kind: String = str(node.get_meta("kind"))
		var body: Sprite2D = node.get_node("Body")
		var top: Vector2 = node.position + Vector2(0, -body.texture.get_height() - 3 + roundf(sin(elapsed * 2.0 + node.position.x) * 1.0))
		if kind in ["npc", "object"]: _bang(top, Color("f0d49c"))
		elif kind == "enemy" and bool(node.get_meta("source").get("alerted", false)): _bang(top, Color("f39579"))
