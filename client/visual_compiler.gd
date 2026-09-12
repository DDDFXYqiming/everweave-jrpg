extends RefCounted
const Library = preload("res://client/asset_library.gd")
## Compile validated model-authored pixel geometry into local GPU textures.

static func color(value: String, palette: Dictionary) -> Color:
	return Color(str(palette.get(value, value)))

static func compile_sprite(recipe: Dictionary, palette: Dictionary) -> Texture2D:
	var width: int = int(recipe.size[0])
	var height: int = int(recipe.size[1])
	var img := Image.create(width, height, false, Image.FORMAT_RGBA8)
	img.fill(Color.TRANSPARENT)
	if recipe.has("asset"):
		var base: Image = Library.get_image(str(recipe.asset),str(recipe.get("asset_hash","")))
		_transform(base,recipe)
		img.blend_rect(base,Rect2i(Vector2i.ZERO,base.get_size()),Vector2i.ZERO)
	for part in recipe.get("parts",[]):
		var layer: Image = Library.get_image(str(part.asset),str(part.get("asset_hash","")))
		_transform(layer,part)
		var scale: int = int(part.get("scale",1))
		if scale != 1: layer.resize(layer.get_width()*scale,layer.get_height()*scale,Image.INTERPOLATE_NEAREST)
		img.blend_rect(layer,Rect2i(Vector2i.ZERO,layer.get_size()),Vector2i(int(part.at[0]),int(part.at[1])))
	if recipe.has("parts"):_transform(img,recipe)
	for command in recipe.get("layers",[]):
		var ink: Color = color(str(command[-1]), palette)
		if command[0] == "poly":
			var points := PackedVector2Array()
			for point in command[1]: points.append(Vector2(float(point[0]), float(point[1])))
			for y in range(height):
				for x in range(width):
					if Geometry2D.is_point_in_polygon(Vector2(x + 0.5, y + 0.5), points): img.set_pixel(x, y, ink)
		else:
			var x0: int = int(command[1])
			var y0: int = int(command[2])
			var w: int = int(command[3])
			var h: int = int(command[4])
			for y in range(y0, mini(height, y0 + h)):
				for x in range(x0, mini(width, x0 + w)):
					var point := Vector2((x + 0.5 - x0) / w * 2.0 - 1.0, (y + 0.5 - y0) / h * 2.0 - 1.0)
					if command[0] == "rect" or point.length_squared() <= 1.0: img.set_pixel(x, y, ink)
	return ImageTexture.create_from_image(img)

static func _transform(img: Image, spec: Dictionary) -> void:
	if bool(spec.get("flip_x",false)): img.flip_x()
	if spec.has("tint"):
		var tint := Color(str(spec.tint))
		for y in range(img.get_height()):
			for x in range(img.get_width()):img.set_pixel(x,y,img.get_pixel(x,y)*tint)

static func compile_tiles(visuals: Dictionary, seed_value: int) -> Texture2D:
	var img := Image.create(160, 16, false, Image.FORMAT_RGBA8)
	var palette: Dictionary = visuals.palette
	var terrain: String = str(visuals.terrain)
	var rng := RandomNumberGenerator.new()
	rng.seed = seed_value
	for kind in range(5):
		var key: String = ["ground", "path", "water", "wall", "path"][kind]
		var base: Color = color(key, palette)
		for variant in range(2):
			for y in range(16):
				for x in range(16):
					var ink: Color = base
					var grain: float = rng.randf()
					if kind == 2:
						if terrain == "void":
							if grain > .983: ink = color("accent", palette).lightened(.3)
						elif (y + variant * 4) % 8 == 2 and (x + y) % 7 < 4: ink = base.lightened(.17)
					elif terrain == "metal" or (kind == 1 and terrain == "void"):
						if x == 0 or y == 0: ink = base.darkened(.28)
						elif (x == 2 or x == 13) and (y == 2 or y == 13): ink = base.lightened(.25)
						elif variant == 1 and x == 7 and y > 4 and y < 12: ink = color("accent", palette).darkened(.15)
					elif terrain == "wood" or kind == 4:
						if y % 5 == 0: ink = base.darkened(.25)
						elif grain > .9: ink = base.lightened(.12)
					elif terrain == "stone" or (kind == 3 and terrain != "void"):
						if y % 8 == 0 or (x + (y / 8) * 8) % 16 == 0: ink = base.darkened(.3)
						elif grain > .92: ink = base.lightened(.1)
					elif terrain == "sand":
						if (y + x / 5 + variant * 3) % 9 == 0: ink = base.lightened(.12)
					elif terrain == "snow":
						if grain > .96: ink = base.lightened(.3)
						elif grain < .025: ink = base.darkened(.08)
					elif terrain == "void":
						if grain > .99: ink = color("accent", palette)
					elif grain > .86: ink = base.lightened(.1)
					img.set_pixel(kind * 32 + variant * 16 + x, y, ink)
	return ImageTexture.create_from_image(img)

static func compile(visuals: Dictionary, seed_value: int) -> Dictionary:
	var compiled: Dictionary = {}
	var animations: Dictionary = {}
	for key in visuals.sprites:
		var recipe: Dictionary = visuals.sprites[key]
		compiled[key] = compile_sprite(recipe, visuals.palette)
		if recipe.has("frames"):
			var frames: Array[Texture2D] = []
			for layers in recipe.frames:
				var frame: Dictionary = recipe.duplicate(true)
				frame.erase("frames")
				frame["layers"] = layers
				frames.append(compile_sprite(frame, visuals.palette))
			animations[key] = {"frames":frames,"frame_ms":int(recipe.get("frame_ms",180))}
	compiled["__animations"] = animations
	for role in visuals.get("bindings", {}):
		if not compiled.has(role):
			compiled[role] = compiled[str(visuals.bindings[role])]
			if animations.has(str(visuals.bindings[role])):animations[role] = animations[str(visuals.bindings[role])]
	# Exits are engine UI affordances, drawn in the region's own palette.
	var gate := {"size":[24,32], "layers":[["rect",3,2,18,28,"shadow"],["rect",5,4,14,24,"accent"],["rect",7,6,10,22,"water"],["rect",1,28,22,3,"path"]]}
	if not compiled.has("portal"): compiled["portal"] = compile_sprite(gate, visuals.palette)
	if not compiled.has("portal_pending"): compiled["portal_pending"] = compiled["portal"]
	if not compiled.has("object"): compiled["object"] = compiled["portal"]
	compiled["__tiles"] = compile_tiles(visuals, seed_value)
	return compiled

static func resolve(key: String, compiled: Dictionary) -> String:
	if compiled.has(key): return key
	if key.begins_with("hero_") and compiled.has("hero"): return "hero"
	if key.begins_with("npc_") and compiled.has("npc"): return "npc"
	if key in ["slime", "wolf", "sentinel", "wisp", "mimic"] and compiled.has("enemy"): return "enemy"
	if key in ["house", "tower", "camp"] and compiled.has("building"): return "building"
	if key in ["tree", "bush", "flower"] and compiled.has("vegetation"): return "vegetation"
	return "object"

static func texture(key: String, compiled: Dictionary, seconds: float) -> Texture2D:
	var resolved: String = resolve(key, compiled)
	var animations: Dictionary = compiled.get("__animations", {})
	if animations.has(resolved):
		var animation: Dictionary = animations[resolved]
		var frames: Array = animation.frames
		return frames[int(seconds * 1000.0 / int(animation.frame_ms)) % frames.size()]
	return compiled[resolved]
