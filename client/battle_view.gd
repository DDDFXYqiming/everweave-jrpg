extends Control
## Small battle stage with shared pixel assets; combat outcomes are server-authoritative.
var atlas: Texture2D = preload("res://assets/atlas.png")
var sprites: Dictionary = {}
var battle: Dictionary = {}
var elapsed: float = 0.0
var hit_flash: float = 0.0
var old_turn: int = -1
const VisualCompiler = preload("res://client/visual_compiler.gd")
var generated: Dictionary = {}
var visuals: Dictionary = {}

func set_visuals(value: Dictionary, seed_value: int) -> void:
	visuals = value
	generated = VisualCompiler.compile(visuals, seed_value) if not visuals.is_empty() else {}

func _ready() -> void:
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	var parsed = JSON.parse_string(FileAccess.get_file_as_string("res://assets/atlas.json"))
	if parsed is Dictionary: sprites = parsed

func update_battle(value: Dictionary) -> void:
	battle = value
	if int(battle.get("turn", 0)) != old_turn:
		old_turn = int(battle.get("turn", 0))
		hit_flash = 0.2
	queue_redraw()

func _process(delta: float) -> void:
	elapsed += delta
	hit_flash = maxf(0, hit_flash - delta)
	queue_redraw()

func sprite(key: String, foot: Vector2, factor: float) -> void:
	if not generated.is_empty():
		var texture: Texture2D = VisualCompiler.texture(key, generated, elapsed)
		var extent: Vector2 = texture.get_size() * factor
		draw_texture_rect(texture, Rect2(foot - Vector2(extent.x * .5, extent.y), extent), false)
		return
	if not sprites.has(key): return
	var data: Array = sprites[key].rect
	var src := Rect2(data[0], data[1], data[2], data[3])
	draw_texture_rect_region(atlas, Rect2(foot - Vector2(src.size.x * factor / 2, src.size.y * factor), src.size * factor), src)

func _draw() -> void:
	var background := Color("182337") if visuals.is_empty() else Color(str(visuals.palette.ground)).darkened(.4)
	draw_rect(Rect2(Vector2.ZERO, size), background)
	for i in range(9):
		var at: float = size.y * 0.55 + i * 12
		draw_line(Vector2(0, at), Vector2(size.x, at), Color(0.33, 0.40, 0.52, 0.12), 1.0)
	for i in range(24):
		var p := Vector2(fmod(i * 57.0 + elapsed * 3, maxf(1, size.x)), fmod(i * 31.0, maxf(1, size.y * 0.5)))
		draw_rect(Rect2(p, Vector2(2, 2)), Color(0.69, 0.78, 0.8, 0.4))
	_ellipse(Vector2(size.x * 0.28, size.y * 0.84), Vector2(65, 15), Color("111b2b"))
	_ellipse(Vector2(size.x * 0.74, size.y * 0.80), Vector2(92, 22), Color("111b2b"))
	sprite("hero_0", Vector2(size.x * 0.28, size.y * 0.86), 4.0)
	sprite(str(battle.get("monster", "sentinel")) if generated.is_empty() else str(battle.get("sprite", "enemy")), Vector2(size.x * 0.74 + sin(elapsed * 2) * 2, size.y * 0.82), 5.0)
	if hit_flash > 0:
		draw_rect(Rect2(Vector2.ZERO, size), Color(0.95, 0.81, 0.70, hit_flash * 0.45))

func _ellipse(center: Vector2, radii: Vector2, color: Color) -> void:
	var points := PackedVector2Array()
	for i in range(32):
		var angle: float = i * TAU / 32.0
		points.append(center + Vector2(cos(angle) * radii.x, sin(angle) * radii.y))
	draw_colored_polygon(points, color)
