extends RefCounted

static var cache: Dictionary = {}

static func _opaque(image: Image, x: int, y: int) -> bool:
	return x >= 0 and y >= 0 and x < image.get_width() and y < image.get_height() and image.get_pixel(x, y).a > 0.5

static func _skin(ink: Color) -> bool:
	return (ink.h < 0.14 or ink.h > 0.95) and ink.s > 0.15 and ink.s < 0.75 and ink.v > 0.5

static func _luma(ink: Color) -> float:
	return ink.r * 0.299 + ink.g * 0.587 + ink.b * 0.114

static func _bounds(image: Image) -> Rect2i:
	var top: int = image.get_height()
	var bottom: int = -1
	var left: int = image.get_width()
	var right: int = -1
	for y in range(image.get_height()):
		for x in range(image.get_width()):
			if image.get_pixel(x, y).a > 0.5:
				top = mini(top, y)
				bottom = maxi(bottom, y)
				left = mini(left, x)
				right = maxi(right, x)
	for _i in range(3):
		if bottom <= top + 4: break
		var colors: Dictionary = {}
		var count: int = 0
		for x in range(left, right + 1):
			if image.get_pixel(x, bottom).a > 0.5:
				colors[image.get_pixel(x, bottom).to_html()] = true
				count += 1
		if colors.size() == 1 and count >= 4: bottom -= 1
		else: break
	return Rect2i(left, top, right - left + 1, bottom - top + 1)

static func _hair(image: Image, box: Rect2i) -> Color:
	var votes: Dictionary = {}
	var rows: int = maxi(2, int(box.size.y * 0.3))
	for y in range(box.position.y, box.position.y + rows):
		for x in range(box.position.x, box.end.x):
			var ink: Color = image.get_pixel(x, y)
			if ink.a < 0.5 or _skin(ink): continue
			if not (_opaque(image, x - 1, y) and _opaque(image, x + 1, y) and _opaque(image, x, y - 1) and _opaque(image, x, y + 1)): continue
			var key: String = ink.to_html()
			votes[key] = votes.get(key, 0) + 1
	var best: String = ""
	for key in votes:
		if best.is_empty() or votes[key] > votes[best]: best = key
	if best.is_empty():
		var ink: Color = image.get_pixel(box.position.x + box.size.x / 2, box.position.y + box.size.y / 2)
		return ink.darkened(0.2) if ink.a > 0.5 else Color(0.3, 0.25, 0.2)
	return Color(best)

static func _cover_face(image: Image, box: Rect2i, from_x: int, to_x: int) -> void:
	var hair: Color = _hair(image, box)
	var head_rows: int = maxi(3, int(box.size.y * 0.5))
	var source: Image = image.duplicate()
	for y in range(box.position.y, box.position.y + head_rows):
		for x in range(maxi(from_x, box.position.x), mini(to_x, box.end.x)):
			var ink: Color = source.get_pixel(x, y)
			if ink.a < 0.5: continue
			var interior: bool = _opaque(source, x - 1, y) and _opaque(source, x + 1, y) and _opaque(source, x, y - 1) and _opaque(source, x, y + 1)
			if _skin(ink) or (interior and absf(_luma(ink) - _luma(hair)) > 0.3):
				var shade: Color = hair.darkened(0.12) if (y - box.position.y) * 2 > head_rows else hair
				shade.a = 1.0
				image.set_pixel(x, y, shade)

static func _shift(image: Image, area: Rect2i, offset: Vector2i) -> void:
	var rect: Rect2i = area.intersection(Rect2i(Vector2i.ZERO, image.get_size()))
	var source: Image = image.duplicate()
	for y in range(rect.position.y, rect.end.y):
		for x in range(rect.position.x, rect.end.x):
			image.set_pixel(x, y, Color.TRANSPARENT)
	for y in range(rect.position.y, rect.end.y):
		for x in range(rect.position.x, rect.end.x):
			var ink: Color = source.get_pixel(x, y)
			var to := Vector2i(x, y) + offset
			if ink.a > 0.0 and to.x >= 0 and to.y >= 0 and to.x < image.get_width() and to.y < image.get_height():
				image.set_pixel(to.x, to.y, ink)

static func _walk(image: Image, box: Rect2i, side: bool, phase: int) -> Image:
	var frame: Image = image.duplicate()
	var leg_rows: int = maxi(2, int(box.size.y * 0.24))
	var leg_top: int = box.end.y - leg_rows
	var middle: int = box.position.x + box.size.x / 2
	var near := Rect2i(box.position.x - 1, leg_top, middle - box.position.x + 1, leg_rows)
	var far := Rect2i(middle, leg_top, box.end.x - middle + 1, leg_rows)
	if phase == 1:
		var swap := near
		near = far
		far = swap
	if side:
		_shift(frame, near, Vector2i(-1, 0))
		_shift(frame, far, Vector2i(1, 0))
	else:
		_shift(frame, near, Vector2i(0, -1))
	return frame

static func frames(texture: Texture2D) -> Dictionary:
	var id: int = texture.get_instance_id()
	if cache.has(id): return cache[id]
	var base: Image = texture.get_image()
	base.convert(Image.FORMAT_RGBA8)
	var image := Image.create(base.get_width(), base.get_height() + 1, false, Image.FORMAT_RGBA8)
	image.fill(Color.TRANSPARENT)
	image.blit_rect(base, Rect2i(Vector2i.ZERO, base.get_size()), Vector2i(0, 1))
	var box: Rect2i = _bounds(image)
	var views: Dictionary = {"down": image}
	var back: Image = image.duplicate()
	_cover_face(back, box, box.position.x, box.end.x)
	views["up"] = back
	var side: Image = image.duplicate()
	_cover_face(side, box, box.position.x, box.position.x + int(box.size.x * 0.5))
	var torso_top: int = box.position.y + maxi(3, int(box.size.y * 0.5))
	_shift(side, Rect2i(box.position.x, torso_top, box.size.x / 2, box.end.y - torso_top), Vector2i(1, 0))
	views["right"] = side
	var result: Dictionary = {}
	for direction in ["down", "up", "right"]:
		var view: Image = views[direction]
		var is_side: bool = direction == "right"
		var cycle: Array[Texture2D] = []
		for step in [-1, 0, -1, 1]:
			cycle.append(ImageTexture.create_from_image(view if step < 0 else _walk(view, box, is_side, step)))
		result[direction] = cycle
	var mirrored: Array[Texture2D] = []
	for texture_frame in result["right"]:
		var flipped: Image = texture_frame.get_image()
		flipped.flip_x()
		mirrored.append(ImageTexture.create_from_image(flipped))
	result["left"] = mirrored
	cache[id] = result
	return result

static func direction(vector: Vector2) -> String:
	if absf(vector.x) > absf(vector.y): return "right" if vector.x > 0 else "left"
	return "down" if vector.y >= 0 else "up"
