extends RefCounted

const Library = preload("res://client/asset_library.gd")
const FIRE_WORDS: Array[String] = ["torch", "fire", "flame", "lamp", "lantern", "candle", "brazier", "campfire", "hearth", "forge", "灯", "火", "烛", "炉", "炬", "篝", "焰", "烬", "hearth"]
const WINDOW_WORDS: Array[String] = ["window", "窗"]
const MAGIC_WORDS: Array[String] = ["crystal", "magic", "rune", "shrine", "altar", "portal", "水晶", "符", "祭坛", "神龛", "法阵"]

static var light_texture: Texture2D

static func _texture() -> Texture2D:
	if light_texture == null:
		var gradient := Gradient.new()
		gradient.set_color(0, Color(1, 1, 1, 1))
		gradient.set_color(1, Color(1, 1, 1, 0))
		gradient.add_point(0.45, Color(1, 1, 1, 0.45))
		var texture := GradientTexture2D.new()
		texture.gradient = gradient
		texture.fill = GradientTexture2D.FILL_RADIAL
		texture.fill_from = Vector2(0.5, 0.5)
		texture.fill_to = Vector2(1.0, 0.5)
		texture.width = 128
		texture.height = 128
		light_texture = texture
	return light_texture

static func _words(key: String, recipe: Dictionary) -> String:
	var text: String = key
	var ids: Array = []
	if recipe.has("asset"): ids.append(str(recipe.asset))
	if recipe.has("base") and recipe.base is Dictionary and recipe.base.has("asset"): ids.append(str(recipe.base.asset))
	for part in recipe.get("parts", []): ids.append(str(part.get("asset", "")))
	for id in ids:
		text += " " + id
		var item: Dictionary = Library.assets.get(id, {})
		text += " " + str(item.get("name", "")) + " " + str(item.get("description", "")) + " " + " ".join(PackedStringArray(item.get("tags", [])))
	return text.to_lower()

static func _hit(text: String, words: Array[String]) -> bool:
	for word in words:
		if text.contains(word): return true
	return false

static func _brightest(texture: Texture2D, fallback: Color) -> Color:
	var image: Image = texture.get_image()
	var best: Color = fallback
	var score: float = 0.0
	for y in range(image.get_height()):
		for x in range(image.get_width()):
			var ink: Color = image.get_pixel(x, y)
			if ink.a < 0.5: continue
			var value: float = ink.v * (0.4 + ink.s)
			if value > score:
				score = value
				best = ink
	best.a = 1.0
	return best.lerp(Color.WHITE, 0.2)

static func _light(color: Color, radius: float, energy: float, flicker: bool, lift: float) -> PointLight2D:
	var light := PointLight2D.new()
	light.texture = _texture()
	light.texture_scale = radius / 64.0
	light.color = color
	light.energy = 0.0
	light.position = Vector2(0, -lift)
	light.blend_mode = Light2D.BLEND_MODE_ADD
	light.set_meta("base_energy", energy)
	light.set_meta("flicker", flicker)
	light.add_to_group("world_light")
	return light

static func for_sprite(key: String, recipe: Dictionary, texture: Texture2D, atmosphere: Dictionary) -> PointLight2D:
	var text: String = _words(key, recipe)
	if _hit(text, FIRE_WORDS): return _light(_brightest(texture, Color(1.0, 0.7, 0.35)).lerp(Color(1.0, 0.68, 0.36), 0.55), 60.0, 1.1, true, texture.get_height() * 0.7)
	if _hit(text, MAGIC_WORDS): return _light(atmosphere.get("accent", Color(0.5, 0.8, 1.0)).lerp(_brightest(texture, Color.WHITE), 0.4), 44.0, 0.8, false, texture.get_height() * 0.5)
	if _hit(text, WINDOW_WORDS): return _light(Color(1.0, 0.78, 0.45), 30.0, 0.55, false, texture.get_height() * 0.5)
	if key in ["portal", "portal_pending"]: return _light(atmosphere.get("accent", Color(0.5, 0.8, 1.0)), 40.0, 0.7, false, 12.0)
	return null

static func lantern(atmosphere: Dictionary) -> PointLight2D:
	var light: PointLight2D = _light(Color(1.0, 0.8, 0.58), 60.0, 0.6, false, 8.0)
	light.set_meta("lantern", true)
	return light

static func refresh(tree: SceneTree, atmosphere: Dictionary, seconds: float) -> int:
	var night: float = float(atmosphere.get("night", 0.0))
	var count: int = 0
	for node in tree.get_nodes_in_group("world_light"):
		var light: PointLight2D = node
		var strength: float = smoothstep(0.08, 0.7, night)
		if bool(light.get_meta("lantern", false)): strength = 1.0 if bool(atmosphere.get("lantern", false)) else 0.0
		var energy: float = float(light.get_meta("base_energy")) * strength
		if bool(light.get_meta("flicker")): energy *= 0.86 + 0.14 * sin(seconds * 11.0 + light.get_instance_id() % 97) * sin(seconds * 3.7)
		light.energy = energy
		light.enabled = energy > 0.01
		if light.enabled: count += 1
	return count
