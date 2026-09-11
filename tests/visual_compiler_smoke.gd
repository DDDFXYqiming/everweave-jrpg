extends SceneTree
const Compiler = preload("res://client/visual_compiler.gd")

func _initialize() -> void:
	var palette := {"ground":"#123456", "path":"#345678", "water":"#091020", "wall":"#223344", "accent":"#abcdef", "shadow":"#010203"}
	var recipe := {"size":[16,24], "layers":[["rect",2,2,8,8,"accent"],["ellipse",2,12,8,8,"#ff0000"],["poly",[[11,1],[15,1],[15,8]],"#00ff00"]]}
	var texture: Texture2D = Compiler.compile_sprite(recipe, palette)
	var pixels: Image = texture.get_image()
	assert(pixels.get_pixel(0,0).a == 0)
	assert(pixels.get_pixel(4,4).to_html(false) == "abcdef")
	assert(pixels.get_pixel(5,15).to_html(false) == "ff0000")
	assert(pixels.get_pixel(14,2).to_html(false) == "00ff00")
	var changed: Dictionary = recipe.duplicate(true)
	changed.layers[0] = ["rect",8,2,7,8,"accent"]
	assert(Compiler.compile_sprite(changed,palette).get_image().get_data() != pixels.get_data())
	var visuals := {"terrain":"metal","palette":palette,"sprites":{"hero":recipe,"npc":recipe,"enemy":recipe,"reactor":recipe},"bindings":{"building":"reactor"}}
	var result: Dictionary = Compiler.compile(visuals,42)
	assert(result.has("building") and result.has("portal") and result.has("__tiles"))
	assert(Compiler.resolve("house",result) == "building")
	print("VISUAL_COMPILER_OK geometry_changes_pixels=true")
	quit(0)
