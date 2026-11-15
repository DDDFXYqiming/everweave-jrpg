extends Node2D

const VisualCompiler = preload("res://client/visual_compiler.gd")
const TILE: int = 16
const RANK := {0: 0, 2: 1, 1: 2, 4: 3, 3: 4}
const WATER_SHADER = preload("res://client/world/shaders/water.gdshader")

var water_cells: Array[Vector2i] = []
var sheet: Texture2D
var sheet_row: int = 0

func build(region: Dictionary, generated: Dictionary, materials) -> void:
	for child in get_children():
		child.queue_free()
	water_cells.clear()
	var width: int = int(region.width)
	var height: int = int(region.height)
	var tiles: Array = region.tiles
	var keys: Array = []
	var types: Dictionary = {}
	var counts: Dictionary = {}
	var grid: Array = []
	for y in range(height):
		var row: Array = []
		for x in range(width):
			var typ: int = int(tiles[y][x])
			var key: String = _key(region, generated, materials, typ, x, y)
			if not types.has(key):
				types[key] = typ
				keys.append(key)
			counts[key] = counts.get(key, 0) + 1
			if typ == 2: water_cells.append(Vector2i(x, y))
			row.append(key)
		grid.append(row)
	keys.sort_custom(func(a: String, b: String) -> bool: return RANK[types[a]] < RANK[types[b]] or (RANK[types[a]] == RANK[types[b]] and counts[a] > counts[b]))
	var rank: Dictionary = {}
	for index in range(keys.size()):
		rank[keys[index]] = index
	var seed_value: int = int(region.get("seed", 0))
	for index in range(keys.size()):
		var key: String = keys[index]
		var typ: int = types[key]
		var source: Dictionary = _sources(key, typ, generated, materials)
		var layer := TileMapLayer.new()
		layer.position = Vector2(-TILE / 2.0, -TILE / 2.0)
		layer.tile_set = _tileset(_atlas(key, typ, source))
		if typ == 2:
			var material := ShaderMaterial.new()
			material.shader = WATER_SHADER
			layer.material = material
		add_child(layer)
		var variants: int = source.bases.size() + source.details.size()
		for j in range(height + 1):
			for i in range(width + 1):
				var mask: int = 0
				var corners: Array[Vector2i] = [Vector2i(i - 1, j - 1), Vector2i(i, j - 1), Vector2i(i - 1, j), Vector2i(i, j)]
				for bit in range(4):
					var c: Vector2i = corners[bit]
					var cell_key: String = grid[clampi(c.y, 0, height - 1)][clampi(c.x, 0, width - 1)]
					if index == 0 or rank[cell_key] == index:
						mask |= 1 << bit
				if mask == 0: continue
				if mask == 15:
					var roll: int = posmod(hash([seed_value, i, j, key]), 1000000)
					var pick: int = (roll / 1000) % source.bases.size()
					if not source.details.is_empty() and roll % 1000 < int(source.density * 1000.0):
						pick = source.bases.size() + (roll / 1000) % source.details.size()
					layer.set_cell(Vector2i(i, j), 0, Vector2i(mini(pick, 15), 1))
				else:
					layer.set_cell(Vector2i(i, j), 0, Vector2i(mask, 0))
	_faces(grid, types, width, height, generated, materials)

func _key(region: Dictionary, generated: Dictionary, materials, typ: int, x: int, y: int) -> String:
	var surfaces: Array = region.get("surfaces", [])
	if not generated.is_empty() and not surfaces.is_empty():
		var surface: String = str(surfaces[y][x])
		if not surface.is_empty() and generated.has(surface):
			if not materials.styles.has(surface): return surface
			if materials.texture(surface, typ, int(region.get("seed", 0)), x, y) != null: return surface
	return "__t%d" % typ

func _image(texture: Texture2D) -> Image:
	var image: Image = texture.get_image()
	image.convert(Image.FORMAT_RGBA8)
	if image.get_size() != Vector2i(TILE, TILE): image.resize(TILE, TILE, Image.INTERPOLATE_NEAREST)
	return image

func _sources(key: String, typ: int, generated: Dictionary, materials) -> Dictionary:
	var bases: Array[Image] = []
	var details: Array[Image] = []
	var density: float = 0.0
	if materials.styles.has(key):
		var style: Dictionary = materials.styles[key]
		for index in range(mini(4, style.base.size())): bases.append(_image(style.base[index]))
		for texture in style.details: details.append(_image(texture))
		density = float(style.density)
	elif key.begins_with("__t"):
		var image: Image = sheet.get_image()
		image.convert(Image.FORMAT_RGBA8)
		for variant in range(2): bases.append(image.get_region(Rect2i(typ * 32 + variant * TILE, sheet_row * TILE, TILE, TILE)))
	else:
		bases.append(_image(VisualCompiler.texture(key, generated, 0.0)))
	while bases.size() + details.size() > 15: details.pop_back()
	return {"bases": bases, "details": details, "density": density}

func _noise(x: int, y: int, salt: int) -> float:
	return float(posmod(hash([x, y, salt]), 2001)) / 1000.0 - 1.0

func _inside(mask: int, px: int, py: int, crisp: bool, salt: int) -> bool:
	var u: float = (float(px) + 0.5) / TILE
	var v: float = (float(py) + 0.5) / TILE
	if crisp:
		var bit: int = (1 if u >= 0.5 else 0) + (2 if v >= 0.5 else 0)
		return mask & (1 << bit) != 0
	var tl: float = 1.0 if mask & 1 else 0.0
	var tr: float = 1.0 if mask & 2 else 0.0
	var bl: float = 1.0 if mask & 4 else 0.0
	var br: float = 1.0 if mask & 8 else 0.0
	var cu: float = clampf(u, 0.0, 1.0)
	var cv: float = clampf(v, 0.0, 1.0)
	var field: float = tl * (1.0 - cu) * (1.0 - cv) + tr * cu * (1.0 - cv) + bl * (1.0 - cu) * cv + br * cu * cv
	var fade: float = clampf(minf(minf(u, 1.0 - u), minf(v, 1.0 - v)) * 5.0, 0.0, 1.0)
	return field > 0.5 + _noise(px, py, salt) * 0.16 * fade

func _atlas(key: String, typ: int, source: Dictionary) -> Image:
	var atlas := Image.create(TILE * 16, TILE * 2, false, Image.FORMAT_RGBA8)
	atlas.fill(Color.TRANSPARENT)
	var crisp: bool = typ in [3, 4]
	var salt: int = hash(key)
	var outline := Color(0, 0, 0, 0.30 if typ in [1, 3, 4] else (0.22 if typ == 2 else 0.0))
	for mask in range(1, 15):
		var base: Image = source.bases[mask % source.bases.size()]
		var inside: Array = []
		for py in range(-1, TILE + 1):
			var row: Array = []
			for px in range(-1, TILE + 1): row.append(_inside(mask, px, py, crisp, salt))
			inside.append(row)
		for py in range(TILE):
			for px in range(TILE):
				var here: bool = inside[py + 1][px + 1]
				var edge: bool = inside[py][px + 1] != here or inside[py + 2][px + 1] != here or inside[py + 1][px] != here or inside[py + 1][px + 2] != here
				var ink: Color = Color.TRANSPARENT
				if here:
					ink = base.get_pixel(px, py)
					if edge: ink = ink.lightened(0.28) if typ == 2 else ink.darkened(0.18 if typ != 0 else 0.08)
				elif edge and outline.a > 0.0:
					ink = outline
				atlas.set_pixel(mask * TILE + px, py, ink)
	var full: Array[Image] = []
	full.append_array(source.bases)
	full.append_array(source.details)
	for index in range(full.size()):
		atlas.blit_rect(full[index], Rect2i(0, 0, TILE, TILE), Vector2i(index * TILE, TILE))
	return atlas

func _tileset(atlas: Image) -> TileSet:
	var tileset := TileSet.new()
	tileset.tile_size = Vector2i(TILE, TILE)
	var source := TileSetAtlasSource.new()
	source.texture = ImageTexture.create_from_image(atlas)
	source.texture_region_size = Vector2i(TILE, TILE)
	for y in range(atlas.get_height() / TILE):
		for x in range(atlas.get_width() / TILE):
			source.create_tile(Vector2i(x, y))
	tileset.add_source(source, 0)
	return tileset

func _faces(grid: Array, types: Dictionary, width: int, height: int, generated: Dictionary, materials) -> void:
	var wall_keys: Array = []
	for key in types:
		if types[key] == 3: wall_keys.append(key)
	if wall_keys.is_empty(): return
	var atlas := Image.create(TILE * 2, TILE * wall_keys.size(), false, Image.FORMAT_RGBA8)
	atlas.fill(Color.TRANSPARENT)
	for row in range(wall_keys.size()):
		var base: Image = _sources(wall_keys[row], 3, generated, materials).bases[0]
		for py in range(TILE):
			for px in range(TILE):
				if py >= 9:
					var ink: Color = base.get_pixel(px, py).darkened(0.42)
					if py == 9: ink = base.get_pixel(px, py).darkened(0.12)
					elif (py - 10) % 3 == 2 or (px + (py / 3) * 5) % 8 == 0: ink = ink.darkened(0.35)
					atlas.set_pixel(px, row * TILE + py, ink)
				if py < 6:
					atlas.set_pixel(TILE + px, row * TILE + py, Color(0, 0, 0, 0.34 * (1.0 - float(py) / 6.0)))
	var layer := TileMapLayer.new()
	layer.tile_set = _tileset(atlas)
	add_child(layer)
	for y in range(height):
		for x in range(width):
			var key: String = grid[y][x]
			if types[key] == 3 and (y == height - 1 or types[grid[y + 1][x]] != 3):
				layer.set_cell(Vector2i(x, y), 0, Vector2i(0, wall_keys.find(key)))
			elif types[key] != 3 and y > 0 and types[grid[y - 1][x]] == 3:
				layer.set_cell(Vector2i(x, y), 0, Vector2i(1, wall_keys.find(grid[y - 1][x])))
