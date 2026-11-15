extends Node2D

const Walking = preload("res://client/walking.gd")
const Lighting = preload("res://client/world/lighting.gd")
const Poses = preload("res://client/world/poses.gd")
const TILE: float = 16.0
const STEP_SECONDS: float = 0.14
const POSED: Array[String] = ["player", "npc", "enemy"]

var sprite_for: Callable
var recipe_for: Callable
var animated_for: Callable
var atmosphere: Dictionary = {}
var actors: Dictionary = {}
var player: Node2D
var player_cell := Vector2.ZERO
var player_tween: Tween
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

func _make(key: String, kind: String, footprint: Array, label: String) -> Node2D:
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
	node.set_meta("kind", kind)
	node.set_meta("dir", "down")
	node.set_meta("walk_until", 0.0)
	add_child(node)
	_skin(node, key, label)
	return node

func _skin(node: Node2D, key: String, label: String) -> void:
	if str(node.get_meta("key")) == key: return
	node.set_meta("key", key)
	var body: Sprite2D = node.get_node("Body")
	var texture: Texture2D = sprite_for.call(key, elapsed)
	var posed: bool = str(node.get_meta("kind")) in POSED and not animated_for.call(key)
	node.set_meta("frames", Poses.frames(texture) if posed else {})
	_pose(node)
	if node.has_node("Glow"): node.get_node("Glow").free()
	var light: PointLight2D = Lighting.for_sprite(key + " " + label, recipe_for.call(key), texture, atmosphere)
	if light != null:
		light.name = "Glow"
		node.add_child(light)

func _pose(node: Node2D) -> void:
	var body: Sprite2D = node.get_node("Body")
	var frames: Dictionary = node.get_meta("frames")
	if frames.is_empty():
		body.texture = sprite_for.call(str(node.get_meta("key")), elapsed)
		body.flip_h = str(node.get_meta("dir")) == "left"
	else:
		var walking: bool = float(node.get_meta("walk_until")) > elapsed
		var cycle: Array = frames[str(node.get_meta("dir"))]
		body.texture = cycle[int(elapsed * 8.0) % 4 if walking else 0]
		body.flip_h = false
	body.offset = Vector2(-floorf(body.texture.get_width() / 2.0), -body.texture.get_height())

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
		node = _make(key, kind, footprint, label)
		node.position = target
		actors[id] = node
	else:
		_skin(node, key, label)
		if node.position.distance_to(target) > 0.5:
			if node.position.distance_to(target) > TILE * 1.6:
				node.position = target
			else:
				node.set_meta("dir", Poses.direction(target - node.position))
				var tween: Tween = node.create_tween()
				tween.tween_property(node, "position", target, STEP_SECONDS * 1.6)
				node.set_meta("walk_until", elapsed + STEP_SECONDS * 1.6 + 0.1)
	node.set_meta("source", source)
	node.set_meta("cell", cell)
	node.set_meta("footprint", footprint)
	var body: Sprite2D = node.get_node("Body")
	body.modulate = Color(0.55, 0.55, 0.55, 0.75) if kind == "chest" and bool(source.get("spent", false)) else Color.WHITE

func _sync_player(p: Dictionary, snap: bool) -> void:
	var cell := Vector2(float(p.get("x", 0)), float(p.get("y", 0)))
	var facing: Array = p.get("facing", [0, 1])
	if player == null:
		player = _make("hero_0", "player", [1, 1], "")
		player.name = "Player"
		player.add_child(Lighting.lantern(atmosphere))
		snap = true
	if snap or cell.distance_to(player_cell) > 1.5:
		if player_tween != null: player_tween.kill()
		player.position = foot(cell)
	elif cell != player_cell:
		if player_tween != null: player_tween.kill()
		player_tween = player.create_tween()
		player_tween.tween_property(player, "position", foot(cell), STEP_SECONDS)
		player.set_meta("walk_until", elapsed + STEP_SECONDS + 0.32)
	player_cell = cell
	player.set_meta("dir", Poses.direction(Vector2(float(facing[0]), float(facing[1]))))

func player_point() -> Vector2:
	return player.position if player != null else Vector2.ZERO

func head_point(entity_id: String) -> Vector2:
	var node: Node2D = player if entity_id.is_empty() else actors.get("entity:" + entity_id, player)
	if node == null: return Vector2.ZERO
	var body: Sprite2D = node.get_node("Body")
	return node.position + Vector2(0, -body.texture.get_height())

func shake(entity_id: String) -> void:
	var node: Node2D = player if entity_id.is_empty() else actors.get("entity:" + entity_id, player)
	if node != null: node.set_meta("shake_until", elapsed + 0.35)

func _face_player(node: Node2D) -> void:
	var cell: Vector2 = node.get_meta("cell")
	var footprint: Array = node.get_meta("footprint")
	var rect: Rect2i = Walking.rect_from_bottom_left({"x": cell.x, "y": cell.y, "footprint": footprint})
	var dx: float = maxf(maxf(rect.position.x - player_cell.x, 0), player_cell.x - (rect.end.x - 1))
	var dy: float = maxf(maxf(rect.position.y - player_cell.y, 0), player_cell.y - (rect.end.y - 1))
	if dx + dy <= 1.0 and float(node.get_meta("walk_until")) <= elapsed:
		node.set_meta("dir", Poses.direction(player_cell + Vector2(0.5, 0.5) - Vector2(rect.position) - Vector2(rect.size) / 2.0))

func _process(delta: float) -> void:
	elapsed += delta
	if player != null:
		_pose(player)
		_jolt(player)
	for id in actors:
		var node: Node2D = actors[id]
		if str(node.get_meta("kind")) == "npc" and player != null: _face_player(node)
		_pose(node)
		_jolt(node)
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

func _jolt(node: Node2D) -> void:
	var body: Sprite2D = node.get_node("Body")
	body.position.x = (1.0 if int(elapsed * 30.0) % 2 == 0 else -1.0) if float(node.get_meta("shake_until", 0.0)) > elapsed else 0.0
