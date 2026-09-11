extends Control
## Atlas-backed pixel renderer. Only validated runtime data reaches this layer.
## All scene placement is data; the LLM never supplies GDScript or resource paths.

signal entity_clicked(entity_id: String)

const TILE: float = 32.0
const VisualCompiler = preload("res://client/visual_compiler.gd")
var generated: Dictionary = {}
var visual_signature: String = ""
const BIOMES: Array[String] = ["forest", "coast", "snow", "desert", "ruins", "industrial", "dream"]
var atlas: Texture2D = preload("res://assets/atlas.png")
var tiles: Texture2D = preload("res://assets/tiles.png")
var sprites: Dictionary = {}
var snapshot: Dictionary = {}
var region: Dictionary = {}
var visual_player := Vector2.ZERO
var target_player := Vector2.ZERO
var camera := Vector2.ZERO
var elapsed: float = 0.0
var walk_frame: int = 0
var current_id: String = ""
var moving: bool = false
var font: Font

func _ready() -> void:
	clip_contents = true
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	mouse_default_cursor_shape = Control.CURSOR_ARROW
	var parsed = JSON.parse_string(FileAccess.get_file_as_string("res://assets/atlas.json"))
	if parsed is Dictionary:
		sprites = parsed
	font = get_theme_default_font()

func update_world(data: Dictionary) -> void:
	snapshot = data
	var value = data.get("region")
	if not value is Dictionary:
		region = {}
		queue_redraw()
		return
	region = value
	var identity: String = JSON.stringify(region.get("visuals", {}))
	if identity != visual_signature:
		visual_signature = identity
		generated = VisualCompiler.compile(region.visuals, int(region.seed)) if region.has("visuals") else {}
	var p: Dictionary = data.get("player", {})
	target_player = Vector2(float(p.get("x", 0)), float(p.get("y", 0)))
	if current_id != str(region.get("id", "")) or visual_player.distance_to(target_player) > 3.0:
		visual_player = target_player
		current_id = str(region.get("id", ""))
	queue_redraw()

func _process(delta: float) -> void:
	elapsed += delta
	moving = visual_player.distance_to(target_player) > 0.025
	visual_player = visual_player.move_toward(target_player, delta * 10.0)
	walk_frame = (1 + int(elapsed * 9.0) % 2) if moving else 0
	if not region.is_empty():
		var world_size := Vector2(float(region.width), float(region.height)) * TILE
		var wanted := (visual_player + Vector2(0.5, 0.5)) * TILE - size * 0.5
		camera = Vector2(clampf(wanted.x, 0.0, maxf(0.0, world_size.x - size.x)), clampf(wanted.y, 0.0, maxf(0.0, world_size.y - size.y)))
	queue_redraw()

func _draw_sprite(key: String, foot: Vector2, scale_factor: float = 2.0, tint: Color = Color.WHITE) -> void:
	if not generated.is_empty():
		var texture: Texture2D = VisualCompiler.texture(key, generated, elapsed)
		var extent: Vector2 = texture.get_size() * scale_factor
		draw_texture_rect(texture, Rect2((foot - Vector2(extent.x * .5, extent.y)).round(), extent), false, tint)
		return
	if not sprites.has(key):
		return
	var rect: Array = sprites[key].rect
	var source := Rect2(float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3]))
	var extent := source.size * scale_factor
	draw_texture_rect_region(atlas, Rect2((foot - Vector2(extent.x * 0.5, extent.y)).round(), extent), source, tint)

func _is_ready(target: String) -> bool:
	for item in snapshot.get("frontier", []):
		if str(item.id) == target:
			return bool(item.ready)
	return true

func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), Color("111e2d"))
	if region.is_empty() or sprites.is_empty():
		for i in range(34):
			var point := Vector2(fmod(i * 53.0 + 19.0, maxf(size.x, 1.0)), fmod(i * 97.0 + elapsed * 6.0, maxf(size.y, 1.0)))
			draw_rect(Rect2(point, Vector2(2, 2)), Color(0.50, 0.78, 0.74, 0.35))
		return
	var biome_index: int = maxi(0, BIOMES.find(str(region.biome)))
	var grid: Array = region.tiles
	var x0: int = maxi(0, int(camera.x / TILE) - 1)
	var y0: int = maxi(0, int(camera.y / TILE) - 1)
	var x1: int = mini(int(region.width), int((camera.x + size.x) / TILE) + 2)
	var y1: int = mini(int(region.height), int((camera.y + size.y) / TILE) + 2)
	for y in range(y0, y1):
		for x in range(x0, x1):
			var typ: int = int(grid[y][x])
			var variant: int = posmod(x * 7 + y * 13, 2)
			if typ == 2:
				variant = (variant + int(elapsed * 1.6)) % 2
			var at := Vector2(x, y) * TILE - camera
			var surfaces: Array = region.get("surfaces", [])
			if not generated.is_empty() and not surfaces.is_empty():
				var surface: String = str(surfaces[y][x])
				if not surface.is_empty() and generated.has(surface):
					draw_texture_rect(VisualCompiler.texture(surface, generated, elapsed), Rect2(at.floor(), Vector2(TILE + 1, TILE + 1)), false)
					continue
			var terrain_texture: Texture2D = tiles if generated.is_empty() else generated["__tiles"]
			draw_texture_rect_region(terrain_texture, Rect2(at.floor(), Vector2(TILE + 1, TILE + 1)), Rect2((typ * 2 + variant) * 16, biome_index * 16 if generated.is_empty() else 0, 16, 16))
	var objects: Array = []
	for prop in region.get("props", []):
		if bool(prop.get("spent", false)): continue
		if float(prop.x) * TILE < camera.x - 140 or float(prop.x) * TILE > camera.x + size.x + 140:
			continue
		if float(prop.y) * TILE < camera.y - 100 or float(prop.y) * TILE > camera.y + size.y + 140:
			continue
		objects.append({"y": float(prop.y), "x": float(prop.x), "sprite": str(prop.get("sprite", prop.kind)), "kind": "prop"})
	for entity in region.get("entities", []):
		var kind: String = str(entity.kind)
		if bool(entity.get("spent", false)) and kind != "chest":
			continue
		var key: String = kind
		if kind == "npc":
			key = "npc_%d_0" % int(entity.get("appearance", 0))
		elif kind == "enemy":
			key = str(entity.get("monster", "slime"))
		elif kind == "exit":
			key = "portal" if _is_ready(str(entity.target)) else "portal_pending"
		elif kind == "chest" and bool(entity.get("spent", false)):
			key = "chest_open"
		if not generated.is_empty() and entity.has("sprite"): key = str(entity.sprite)
		objects.append({"y": float(entity.y), "x": float(entity.x), "sprite": key, "kind": kind, "entity": entity})
	objects.append({"y": visual_player.y, "x": visual_player.x, "sprite": "hero_%d" % walk_frame, "kind": "player"})
	objects.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return float(a.y) < float(b.y))
	for obj in objects:
		var foot := (Vector2(float(obj.x), float(obj.y)) + Vector2(0.5, 1.0)) * TILE - camera
		var tint := Color.WHITE
		if generated.is_empty() and obj.kind == "prop" and obj.sprite in ["tree", "bush"]:
			if region.biome == "snow":
				tint = Color("c9deed")
			elif region.biome == "dream":
				tint = Color("cba8ed")
			elif region.biome == "desert":
				tint = Color("d8bc85")
		if obj.kind in ["exit", "shrine"]:
			draw_circle(foot - Vector2(0, 17), 24 + 2 * sin(elapsed * 2), Color(0.4, 0.85, 0.8, 0.06))
		if obj.kind == "enemy":
			draw_arc(foot - Vector2(0, 8), 19, 0, TAU, 20, Color(0.91, 0.49, 0.50, 0.65), 1.0)
		if obj.kind == "chest" and bool(obj.entity.get("spent", false)): tint = Color(.55, .55, .55, .7)
		_draw_sprite(str(obj.sprite), foot, 2.0, tint)
		if obj.kind in ["npc", "object"] and obj.has("entity"):
			var marker := foot - Vector2(0, 64 + sin(elapsed * 2 + float(obj.x)) * 2)
			draw_rect(Rect2(marker - Vector2(2, 7), Vector2(4, 8)), Color("f0d49c"))
			draw_rect(Rect2(marker + Vector2(-2, 4), Vector2(4, 3)), Color("f0d49c"))
	var hour: float = fmod(float(snapshot.get("time", 480)), 1440.0) / 60.0
	if hour >= 19.0 or hour < 6.0:
		draw_rect(Rect2(Vector2.ZERO, size), Color(0.035, 0.04, 0.16, 0.25))
	_draw_weather(str(region.get("weather", "clear")))
	_draw_minimap()
	_draw_nearby_hint()

func _draw_weather(weather: String) -> void:
	if weather == "rain":
		draw_rect(Rect2(Vector2.ZERO, size), Color(0.05, 0.12, 0.24, 0.13))
		for i in range(100):
			var x := fmod(i * 83.7 - elapsed * 75.0, maxf(1.0, size.x + 40.0))
			if x < 0: x += size.x + 40.0
			var y := fmod(i * 47.3 + elapsed * 300.0, maxf(1.0, size.y + 40.0))
			draw_line(Vector2(x, y), Vector2(x - 4, y + 13), Color(0.70, 0.84, 0.91, 0.32), 1.0)
	elif weather == "snow" or weather == "fireflies":
		for i in range(48):
			var x := fmod(i * 79.7 + sin(elapsed * 0.6 + i) * 15 + size.x, maxf(1.0, size.x))
			var y := fmod(i * 61.3 + elapsed * (19.0 if weather == "snow" else -6.0) + size.y * 50.0, maxf(1.0, size.y))
			var tint := Color(0.84, 0.91, 0.92, 0.60) if weather == "snow" else Color(0.79, 0.94, 0.62, 0.25 + 0.35 * absf(sin(elapsed + i)))
			draw_rect(Rect2(Vector2(x, y), Vector2(2, 2)), tint)
	elif weather == "fog":
		for i in range(7):
			var top: float = fmod(i * 103.0 + elapsed * 5.0, maxf(1.0, size.y))
			draw_rect(Rect2(0, top, size.x, 45), Color(0.62, 0.72, 0.80, 0.055))

func _draw_minimap() -> void:
	var origin := Vector2(size.x - 126.0, 14.0)
	draw_rect(Rect2(origin - Vector2(5, 5), Vector2(114, 82)), Color(0.035, 0.075, 0.13, 0.89))
	var palette: Array[Color] = [Color("375e59"), Color("b29e75"), Color("356c7b"), Color("293844"), Color("bd9866")]
	if region.has("visuals"):
		palette.clear()
		for key in ["ground", "path", "water", "wall", "path"]: palette.append(Color(str(region.visuals.palette[key])))
	var map_scale: float = minf(104.0 / float(region.width), 72.0 / float(region.height))
	for y in range(int(region.height)):
		for x in range(int(region.width)):
			draw_rect(Rect2(origin + Vector2(x, y) * map_scale, Vector2.ONE * maxf(1.0, map_scale)), palette[int(region.tiles[y][x])])
	for e in region.entities:
		if e.kind == "exit":
			draw_rect(Rect2(origin + Vector2(float(e.x), float(e.y)) * map_scale - Vector2.ONE, Vector2(3, 3)), Color("c1a9ef"))
	draw_rect(Rect2(origin + target_player * map_scale - Vector2.ONE, Vector2(4, 4)), Color("f7e0a4"))

func _draw_nearby_hint() -> void:
	var p: Dictionary = snapshot.get("player", {})
	for e in region.get("entities", []):
		if bool(e.get("spent", false)): continue
		if absf(float(e.x) - float(p.get("x", 0))) + absf(float(e.y) - float(p.get("y", 0))) <= 1.0:
			var text: String = "E  ·  " + str(e.name)
			var width: float = minf(size.x - 40, font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, 16).x + 28)
			var at := Vector2((size.x - width) / 2, size.y - 48)
			draw_rect(Rect2(at, Vector2(width, 34)), Color(0.035, 0.075, 0.13, 0.93))
			draw_string(font, at + Vector2(14, 23), text, HORIZONTAL_ALIGNMENT_LEFT, width - 24, 16, Color("e6dcbf"))
			return

func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		var cell: Vector2 = ((event.position + camera) / TILE).floor()
		for e in region.get("entities", []):
			if int(e.x) == int(cell.x) and int(e.y) == int(cell.y):
				entity_clicked.emit(str(e.id))
				accept_event()
				return
