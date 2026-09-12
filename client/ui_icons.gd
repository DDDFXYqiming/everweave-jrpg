extends RefCounted
## Small original interface symbols; world/item artwork remains model-authored.
static var cache: Dictionary = {}

static func get_icon(name: String) -> Texture2D:
	if cache.has(name): return cache[name]
	var shapes: Dictionary = {
		"bag": '<path d="M8 7V5a4 4 0 0 1 8 0v2M5 8h14l1 13H4L5 8zM8 13h8v5H8zM8 8v2m8-2v2"/>',
		"book": '<path d="M12 5C8 2 4 3 2 4v16c4-2 7-1 10 1 3-2 6-3 10-1V4c-3-1-7-2-10 1v16M5 8l4 1m-4 3 4 1m6-4 4-1m-4 5 4-1"/>',
		"settings": '<path d="M3 6h18M3 12h18M3 18h18M7 3v6m10 0v6M9 15v6"/>',
		"compass": '<circle cx="12" cy="12" r="10"/><path d="m16 7-2 7-6 3 2-7 6-3zM12 0v3m0 18v3M0 12h3m18 0h3"/>',
		"consumable": '<path d="M9 2h6m-5 0v6L5 18c-1 2 0 4 2 4h10c2 0 3-2 2-4L14 8V2M7 15h10"/>',
		"weapon": '<path d="m18 2 4 0 0 4-12 12-4-4L18 2zM4 12l8 8M2 22l5-5m-5 2 3 3"/>',
		"charm": '<path d="m12 2 8 7-8 13L4 9l8-7zM4 9h16M12 2 8 9l4 13 4-13-4-7"/>',
		"key": '<circle cx="8" cy="8" r="5"/><path d="m12 12 10 10m-4-4 3-3m-6 0 3-3"/>',
		"tool": '<path d="M14 3a6 6 0 0 0-7 8L2 17a3 3 0 0 0 5 5l6-8a6 6 0 0 0 8-7l-5 3-3-3 1-4z"/>',
		"sound": '<path d="M3 9h4l5-5v16l-5-5H3V9zm13-2c3 3 3 7 0 10m3-13c5 5 5 11 0 16"/>',
		"screen": '<path d="M9 3H3v6m12-6h6v6M3 15v6h6m6 0h6v-6"/>',
		"close": '<path d="m5 5 14 14M19 5 5 19"/>',
	}
	var svg: String = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="-1 -1 26 26"><g fill="none" stroke="#d9c49a" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">' + str(shapes.get(name, shapes.bag)) + '</g></svg>'
	var img := Image.new()
	img.load_svg_from_string(svg, 2.0)
	cache[name] = ImageTexture.create_from_image(img)
	return cache[name]
