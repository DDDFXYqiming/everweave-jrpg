extends CanvasLayer

const FOG_SHADER = preload("res://client/world/shaders/fog.gdshader")

var kind: String = ""
var view_size := Vector2(320, 200)
var elapsed: float = 0.0
var painter: Node2D

func _ready() -> void:
	painter = Node2D.new()
	painter.draw.connect(_paint)
	add_child(painter)

func configure(weather: String, size: Vector2) -> void:
	if weather == kind and size == view_size: return
	kind = weather
	view_size = size
	painter.queue_redraw()
	for child in get_children():
		if child != painter: child.queue_free()
	if weather == "fog":
		var fog := ColorRect.new()
		fog.size = size
		fog.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var material := ShaderMaterial.new()
		material.shader = FOG_SHADER
		material.set_shader_parameter("pixels", size)
		fog.material = material
		add_child(fog)

func _process(delta: float) -> void:
	elapsed += delta
	if kind in ["rain", "snow", "fireflies"]: painter.queue_redraw()

func _wrap(value: float, span: float) -> float:
	return fposmod(value, span)

func _paint() -> void:
	var span := view_size + Vector2(32, 32)
	if kind == "rain":
		var count: int = int(view_size.x * 0.55)
		for i in range(count):
			var speed: float = 260.0 + float(i % 7) * 18.0
			var y: float = _wrap(i * 47.3 + elapsed * speed, span.y) - 16.0
			var x: float = _wrap(i * 83.7 - elapsed * speed * 0.22, span.x) - 16.0
			var ink := Color(0.72, 0.82, 0.96, 0.38 + 0.2 * float(i % 3) / 2.0)
			for step in range(4):
				painter.draw_rect(Rect2(Vector2(floorf(x - step * 0.25), floorf(y + step)), Vector2(1, 1)), ink)
		for i in range(int(view_size.x * 0.08)):
			var phase: float = fposmod(elapsed * 3.0 + i * 0.37, 1.0)
			if phase > 0.35: continue
			var cell: int = int(elapsed * 3.0 + i * 0.37)
			var at := Vector2(posmod(hash([i, cell]), maxi(1, int(view_size.x))), posmod(hash([cell, i, 7]), maxi(1, int(view_size.y))))
			var spread: float = 1.0 + floorf(phase * 6.0)
			painter.draw_rect(Rect2(at + Vector2(-spread, 0), Vector2(1, 1)), Color(0.8, 0.88, 1.0, 0.5))
			painter.draw_rect(Rect2(at + Vector2(spread, 0), Vector2(1, 1)), Color(0.8, 0.88, 1.0, 0.5))
	elif kind == "snow":
		var count: int = int(view_size.x * 0.4)
		for i in range(count):
			var speed: float = 12.0 + float(i % 5) * 4.0
			var y: float = _wrap(i * 61.3 + elapsed * speed, span.y) - 16.0
			var x: float = _wrap(i * 79.7 + sin(elapsed * 0.7 + i) * 6.0 + elapsed * 4.0, span.x) - 16.0
			var extent: float = 2.0 if i % 6 == 0 else 1.0
			painter.draw_rect(Rect2(Vector2(x, y).floor(), Vector2(extent, extent)), Color(0.95, 0.97, 1.0, 0.85))
	elif kind == "fireflies":
		for i in range(26):
			var x: float = _wrap(i * 97.1 + sin(elapsed * 0.35 + i * 1.7) * 18.0, view_size.x)
			var y: float = _wrap(i * 53.9 + cos(elapsed * 0.27 + i) * 12.0 - elapsed * 2.0, view_size.y)
			var glow: float = clampf(sin(elapsed * 1.6 + i * 2.1) * 0.8 + 0.4, 0.0, 1.0)
			if glow <= 0.05: continue
			painter.draw_rect(Rect2(Vector2(x, y).floor(), Vector2(1, 1)), Color(0.88, 1.0, 0.55, glow))
			painter.draw_rect(Rect2(Vector2(x - 1, y - 1).floor(), Vector2(3, 3)), Color(0.88, 1.0, 0.55, glow * 0.18))
