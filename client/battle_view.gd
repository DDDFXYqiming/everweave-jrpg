extends Control
var atlas: Texture2D = preload("res://assets/atlas.png")
var sprites: Dictionary = {}
var battle: Dictionary = {}
var elapsed: float = 0.0
var old_turn: int = -1
var old_hp: int = -1
const VisualCompiler = preload("res://client/visual_compiler.gd")
const FLASH_SHADER = preload("res://client/world/shaders/flash.gdshader")
var generated: Dictionary = {}
var visuals: Dictionary = {}
var hero: TextureRect
var enemy: TextureRect

func set_visuals(value: Dictionary, seed_value: int) -> void:
	visuals = value
	generated = VisualCompiler.compile(visuals, seed_value) if not visuals.is_empty() else {}

func _actor() -> TextureRect:
	var rect := TextureRect.new()
	rect.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	rect.stretch_mode = TextureRect.STRETCH_SCALE
	rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var material := ShaderMaterial.new()
	material.shader = FLASH_SHADER
	rect.material = material
	add_child(rect)
	return rect

func _ready() -> void:
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	var parsed = JSON.parse_string(FileAccess.get_file_as_string("res://assets/atlas.json"))
	if parsed is Dictionary: sprites = parsed
	hero = _actor()
	enemy = _actor()

func _strike(target: TextureRect) -> void:
	var material: ShaderMaterial = target.material
	var tween: Tween = create_tween()
	tween.tween_method(func(value: float) -> void: material.set_shader_parameter("flash", value), 1.0, 0.0, 0.32)
	target.set_meta("shake_until", elapsed + 0.25)

func update_battle(value: Dictionary) -> void:
	battle = value
	var hp: int = int(battle.get("hp", 0))
	if int(battle.get("turn", 0)) != old_turn:
		if old_turn >= 0: _strike(enemy if hp < old_hp else hero)
		old_turn = int(battle.get("turn", 0))
	old_hp = hp
	queue_redraw()

func _texture(key: String) -> Texture2D:
	if not generated.is_empty(): return VisualCompiler.texture(key, generated, elapsed)
	if not sprites.has(key): return null
	var data: Array = sprites[key].rect
	var texture := AtlasTexture.new()
	texture.atlas = atlas
	texture.region = Rect2(data[0], data[1], data[2], data[3])
	return texture

func _pose(rect: TextureRect, key: String, foot: Vector2, factor: int) -> void:
	var texture: Texture2D = _texture(key)
	rect.texture = texture
	if texture == null: return
	var extent: Vector2 = texture.get_size() * factor
	var shake: float = 0.0
	if float(rect.get_meta("shake_until", 0.0)) > elapsed: shake = 3.0 * (1 if int(elapsed * 40.0) % 2 == 0 else -1)
	rect.position = (foot - Vector2(extent.x * .5 - shake, extent.y)).round()
	rect.size = extent

func _process(delta: float) -> void:
	elapsed += delta
	_pose(hero, "hero_0", Vector2(size.x * 0.28, size.y * 0.86), 4)
	_pose(enemy, str(battle.get("monster", "sentinel")) if generated.is_empty() else str(battle.get("sprite", "enemy")), Vector2(size.x * 0.74, size.y * 0.82 + roundf(sin(elapsed * 2) * 2) * 2), 5)
	queue_redraw()

func _draw() -> void:
	var background := Color("182337") if visuals.is_empty() else Color(str(visuals.palette.ground)).darkened(.4)
	draw_rect(Rect2(Vector2.ZERO, size), background)
	for i in range(9):
		var at: float = floorf(size.y * 0.55 / 4.0) * 4.0 + i * 12
		draw_rect(Rect2(0, at, size.x, 2), Color(0.33, 0.40, 0.52, 0.12))
	for i in range(24):
		var p := Vector2(fmod(i * 57.0 + elapsed * 3, maxf(1, size.x)), fmod(i * 31.0, maxf(1, size.y * 0.5))).floor()
		draw_rect(Rect2(p, Vector2(4, 4)), Color(0.69, 0.78, 0.8, 0.4))
	_ellipse(Vector2(size.x * 0.28, size.y * 0.84), Vector2(64, 16), Color("111b2b"))
	_ellipse(Vector2(size.x * 0.74, size.y * 0.80), Vector2(92, 20), Color("111b2b"))

func _ellipse(center: Vector2, radii: Vector2, color: Color) -> void:
	var step: float = 4.0
	for row in range(-int(radii.y / step), int(radii.y / step) + 1):
		var y: float = row * step
		var half: float = floorf(radii.x * sqrt(maxf(0.0, 1.0 - pow(y / radii.y, 2))) / step) * step
		draw_rect(Rect2((center + Vector2(-half, y - step * 0.5)).floor(), Vector2(half * 2.0, step)), color)
