extends Control
const L = preload("res://client/i18n.gd")

signal entity_clicked(entity_id: String)
signal cell_clicked(cell: Vector2i)
signal map_requested()

const TILE: float = 16.0
const VisualCompiler = preload("res://client/visual_compiler.gd")
const TerrainMaterials = preload("res://client/terrain_materials.gd")
const Walking = preload("res://client/walking.gd")
const Atmosphere = preload("res://client/world/atmosphere.gd")
const Lighting = preload("res://client/world/lighting.gd")
const Terrain = preload("res://client/world/terrain.gd")
const Actors = preload("res://client/world/actors.gd")
const Weather = preload("res://client/world/weather.gd")
const POST_SHADER = preload("res://client/world/shaders/post.gdshader")
const BIOMES: Array[String] = ["forest", "coast", "snow", "desert", "ruins", "industrial", "dream"]
const MINIMAP := Rect2(-222, 76, 204, 158)

var materials = TerrainMaterials.new()
var generated: Dictionary = {}
var snapshot: Dictionary = {}
var region: Dictionary = {}
var atmosphere: Dictionary = {}
var atlas: Texture2D = preload("res://assets/atlas.png")
var tiles: Texture2D = preload("res://assets/tiles.png")
var atlas_rects: Dictionary = {}
var atlas_cache: Dictionary = {}
var visual_signature: String = ""
var terrain_token: String = ""
var current_id: String = ""
var walk_goal := Vector2i(-1, -1):
	set(value):
		walk_goal = value
		if actors != null: actors.walk_goal = value
var font: Font
var pixel_scale: int = 3
var elapsed: float = 0.0
var viewport: SubViewport
var display: TextureRect
var post: ShaderMaterial
var stage: Node2D
var shade: CanvasModulate
var terrain: Terrain
var actors: Actors
var weather: Weather
var camera: Camera2D
var overlay: Control
var view_center := Vector2.ZERO
var fade: float = 0.0
var fade_tween: Tween

func _ready() -> void:
	clip_contents = true
	mouse_default_cursor_shape = Control.CURSOR_ARROW
	var parsed = JSON.parse_string(FileAccess.get_file_as_string("res://assets/atlas.json"))
	if parsed is Dictionary: atlas_rects = parsed
	font = get_theme_default_font()
	viewport = SubViewport.new()
	viewport.snap_2d_transforms_to_pixel = true
	viewport.snap_2d_vertices_to_pixel = true
	viewport.canvas_item_default_texture_filter = Viewport.DEFAULT_CANVAS_ITEM_TEXTURE_FILTER_NEAREST
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	viewport.disable_3d = true
	add_child(viewport)
	stage = Node2D.new()
	viewport.add_child(stage)
	shade = CanvasModulate.new()
	stage.add_child(shade)
	terrain = Terrain.new()
	stage.add_child(terrain)
	actors = Actors.new()
	actors.sprite_for = _sprite
	actors.recipe_for = _recipe
	stage.add_child(actors)
	camera = Camera2D.new()
	stage.add_child(camera)
	camera.make_current()
	weather = Weather.new()
	viewport.add_child(weather)
	display = TextureRect.new()
	display.texture = viewport.get_texture()
	display.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	display.stretch_mode = TextureRect.STRETCH_SCALE
	display.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	display.mouse_filter = Control.MOUSE_FILTER_IGNORE
	post = ShaderMaterial.new()
	post.shader = POST_SHADER
	display.material = post
	add_child(display)
	overlay = Control.new()
	overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
	overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	overlay.draw.connect(_draw_overlay)
	add_child(overlay)
	resized.connect(_layout)
	_layout()

func _layout() -> void:
	if viewport == null: return
	pixel_scale = maxi(1, int(size.y / 240.0))
	var pixels := Vector2i(ceili(maxf(size.x, 1.0) / pixel_scale), ceili(maxf(size.y, 1.0) / pixel_scale))
	viewport.size = pixels
	display.position = Vector2.ZERO
	display.size = Vector2(pixels * pixel_scale)
	post.set_shader_parameter("pixels", Vector2(pixels))
	if not atmosphere.is_empty(): weather.configure(str(atmosphere.weather), Vector2(pixels))

func _sprite(key: String, seconds: float) -> Texture2D:
	if not generated.is_empty(): return VisualCompiler.texture(key, generated, seconds)
	if not atlas_cache.has(key):
		var rect: Array = atlas_rects.get(key, atlas_rects.get("chest", {"rect": [0, 0, 16, 16]})).rect
		var texture := AtlasTexture.new()
		texture.atlas = atlas
		texture.region = Rect2(float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3]))
		atlas_cache[key] = texture
	return atlas_cache[key]

func _recipe(key: String) -> Dictionary:
	if generated.is_empty(): return {}
	return region.get("visuals", {}).get("sprites", {}).get(VisualCompiler.resolve(key, generated), {})

func update_world(data: Dictionary) -> void:
	snapshot = data
	var value = data.get("region")
	if not value is Dictionary:
		region = {}
		stage.visible = false
		overlay.queue_redraw()
		return
	region = value
	stage.visible = true
	var regenerate: bool = false
	var token: String = str(data.get("region_static_token", ""))
	if token.is_empty() or token != terrain_token:
		var identity: String = JSON.stringify([region.get("seed", 0), region.get("visuals", {})])
		if identity != visual_signature:
			visual_signature = identity
			generated = VisualCompiler.compile(region.visuals, int(region.seed)) if region.has("visuals") else {}
			if region.has("visuals"): materials.configure(region.visuals)
		terrain.sheet = tiles if generated.is_empty() else generated["__tiles"]
		terrain.sheet_row = maxi(0, BIOMES.find(str(region.get("biome", "")))) if generated.is_empty() else 0
		terrain.build(region, generated, materials)
		terrain_token = token
		regenerate = true
	atmosphere = Atmosphere.derive(region, float(data.get("time", 480)))
	var entering: bool = str(region.get("id", "")) != current_id
	if entering:
		print("ATMOSPHERE ", JSON.stringify({"region": region.get("id", ""), "name": region.get("name", "")}), " ", Atmosphere.summary(atmosphere))
		if not current_id.is_empty(): _transition()
		current_id = str(region.get("id", ""))
	shade.color = atmosphere.ambient
	post.set_shader_parameter("grade", Vector3(atmosphere.grade.r, atmosphere.grade.g, atmosphere.grade.b))
	post.set_shader_parameter("grade_strength", atmosphere.grade_strength)
	post.set_shader_parameter("saturation", atmosphere.saturation)
	post.set_shader_parameter("wet", atmosphere.wet)
	post.set_shader_parameter("vignette", 0.3 + 0.2 * float(atmosphere.night))
	weather.configure(str(atmosphere.weather), Vector2(viewport.size))
	actors.atmosphere = atmosphere
	actors.has_visuals = not generated.is_empty()
	actors.walk_goal = walk_goal
	actors.sync(data, regenerate or entering)
	_follow(1.0 if entering or regenerate else 0.0)
	overlay.queue_redraw()

func _transition() -> void:
	if fade_tween != null: fade_tween.kill()
	fade = 1.0
	fade_tween = create_tween()
	fade_tween.tween_property(self, "fade", 0.0, 0.55).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)

func _follow(weight: float) -> void:
	if region.is_empty(): return
	var world := Vector2(float(region.width), float(region.height)) * TILE
	var half := Vector2(viewport.size) * 0.5
	var wanted: Vector2 = actors.player_point() - Vector2(0, TILE * 0.5)
	var target := Vector2(
		world.x * 0.5 if world.x <= half.x * 2.0 else clampf(wanted.x, half.x, world.x - half.x),
		world.y * 0.5 if world.y <= half.y * 2.0 else clampf(wanted.y, half.y, world.y - half.y))
	view_center = view_center.lerp(target, weight)
	camera.position = view_center.round()

func _process(delta: float) -> void:
	elapsed += delta
	if region.is_empty():
		overlay.queue_redraw()
		return
	_follow(1.0 - exp(-delta * 7.0))
	post.set_shader_parameter("fade", fade)
	Lighting.refresh(get_tree(), atmosphere, elapsed)
	overlay.queue_redraw()

func _cell_at(point: Vector2) -> Vector2:
	var pixel: Vector2 = point / float(pixel_scale)
	return ((viewport.canvas_transform.affine_inverse() * pixel) / TILE).floor()

func _minimap_rect() -> Rect2:
	return Rect2(Vector2(size.x + MINIMAP.position.x, MINIMAP.position.y), MINIMAP.size)

func _draw_overlay() -> void:
	if region.is_empty():
		overlay.draw_rect(Rect2(Vector2.ZERO, size), Color("131d18"))
		for i in range(34):
			var point := Vector2(fmod(i * 53.0 + 19.0, maxf(size.x, 1.0)), fmod(i * 97.0 + elapsed * 6.0, maxf(size.y, 1.0)))
			overlay.draw_rect(Rect2(point.floor(), Vector2(3, 3)), Color(0.50, 0.78, 0.74, 0.35))
		return
	_draw_minimap()
	_draw_nearby_hint()

func _draw_minimap() -> void:
	var frame: Rect2 = _minimap_rect()
	var origin: Vector2 = frame.position + Vector2(6, 6)
	var hovered: bool = frame.has_point(get_local_mouse_position())
	var opacity: float = 1.0 if hovered else .85
	overlay.draw_rect(frame, Color(0.035, 0.06, 0.09, 0.92 * opacity))
	overlay.draw_rect(frame.grow(-1), Color(Color("d7c59d"), .55 * opacity), false, 2.0)
	var palette: Array[Color] = [Color("375e59"), Color("b29e75"), Color("356c7b"), Color("293844"), Color("bd9866")]
	if region.has("visuals"):
		palette.clear()
		for key in ["ground", "path", "water", "wall", "path"]: palette.append(Color(str(region.visuals.palette[key])))
	for i in range(palette.size()): palette[i].a = opacity
	var map_scale: float = floorf(minf(192.0 / float(region.width), 134.0 / float(region.height)) * 2.0) / 2.0
	map_scale = maxf(map_scale, 1.0)
	for y in range(int(region.height)):
		for x in range(int(region.width)):
			overlay.draw_rect(Rect2(origin + Vector2(x, y) * map_scale, Vector2.ONE * map_scale), palette[int(region.tiles[y][x])])
	for e in region.entities:
		if e.kind == "exit":
			overlay.draw_rect(Rect2((origin + Vector2(float(e.x), float(e.y)) * map_scale - Vector2.ONE).floor(), Vector2(3, 3)), Color("c1a9ef"))
	var p: Dictionary = snapshot.get("player", {})
	overlay.draw_rect(Rect2((origin + Vector2(float(p.get("x", 0)), float(p.get("y", 0))) * map_scale - Vector2(2, 2)).floor(), Vector2(5, 5)), Color("f7e0a4"))
	overlay.draw_string(font, origin + Vector2(3, 146), L.t("旅图 · G") if hovered else "G", HORIZONTAL_ALIGNMENT_LEFT, 120, 12, Color(Color("d7c59d"), opacity))

func _draw_nearby_hint() -> void:
	if not snapshot.get("ui", {}).is_empty() or snapshot.get("battle") is Dictionary: return
	var p: Dictionary = snapshot.get("player", {})
	for e in region.get("entities", []):
		if bool(e.get("spent", false)): continue
		if _distance_to_object(e, Vector2(float(p.get("x", 0)), float(p.get("y", 0)))) <= 1:
			var text: String = "E  ·  " + str(e.name)
			var width: float = minf(size.x - 40, font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, 24).x + 32)
			var at := Vector2(floorf((size.x - width) / 2), size.y - 100)
			overlay.draw_rect(Rect2(at, Vector2(width, 40)), Color(0.035, 0.06, 0.09, 0.94))
			overlay.draw_rect(Rect2(at, Vector2(width, 40)).grow(-1), Color("d7c59d"), false, 2.0)
			overlay.draw_string(font, at + Vector2(16, 29), text, HORIZONTAL_ALIGNMENT_LEFT, width - 28, 24, Color("efe3c2"))
			return

func _distance_to_object(e: Dictionary, p: Vector2) -> float:
	var rect: Rect2i = Walking.rect_from_bottom_left(e)
	var dx: float = maxf(maxf(rect.position.x - p.x, 0), p.x - (rect.end.x - 1))
	var dy: float = maxf(maxf(rect.position.y - p.y, 0), p.y - (rect.end.y - 1))
	return dx + dy

func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion:
		mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND if _minimap_rect().has_point(event.position) else Control.CURSOR_ARROW
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		if _minimap_rect().has_point(event.position):
			map_requested.emit()
			accept_event()
			return
		if region.is_empty(): return
		var cell: Vector2 = _cell_at(event.position)
		for e in region.get("entities", []):
			if _distance_to_object(e, cell) == 0:
				entity_clicked.emit(str(e.id))
				accept_event()
				return
		if cell.x >= 0 and cell.y >= 0 and cell.x < float(region.get("width", 0)) and cell.y < float(region.get("height", 0)):
			cell_clicked.emit(Vector2i(cell))
			accept_event()
