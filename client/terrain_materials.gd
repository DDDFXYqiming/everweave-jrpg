extends RefCounted
## Presentation-only material sampling. No collision, placement or model requests.
const Compiler = preload("res://client/visual_compiler.gd")
const Library = preload("res://client/asset_library.gd")
var styles: Dictionary = {}
var palette: Dictionary = {}
var definitions: Dictionary = {}

func recipe(raw: Dictionary) -> Dictionary:
	var result: Dictionary = raw.duplicate(true)
	if not result.has("size"):
		result.size = Library.entry(str(result.asset)).size if result.has("asset") else [16,16]
	return result

func configure(visuals: Dictionary) -> void:
	styles.clear()
	palette = visuals.get("palette",{})
	definitions = JSON.parse_string(FileAccess.get_file_as_string("res://assets/library/materials.json"))
	for key in visuals.get("sprites",{}):
		var sprite: Dictionary = visuals.sprites[key]
		var style: Dictionary = {}
		if sprite.has("material"):
			style = sprite
		elif sprite.has("asset") and not sprite.has("layers") and not sprite.has("parts") and not sprite.has("frames") and not sprite.has("tint") and not sprite.has("flip_x"):
			for id in definitions:
				if str(sprite.asset) in definitions[id].get("legacy_assets",[]):
					style = definitions[id].duplicate(true)
					style.legacy = true
					break
		if not style.is_empty():styles[key] = compile_style(style)

func compile_style(style: Dictionary) -> Dictionary:
	var bases: Array[Texture2D] = []
	var details: Array[Texture2D] = []
	var img: Image = Compiler.compile_sprite(recipe(style.base),palette).get_image()
	var rng := RandomNumberGenerator.new()
	rng.seed = hash(JSON.stringify(style))
	for index in range(8):
		var textured: Image = img.duplicate()
		for y in range(textured.get_height()):
			for x in range(textured.get_width()):
				var c: Color = textured.get_pixel(x,y)
				var amount: float = rng.randf_range(-1,1)*float(style.get("grain",.025))
				textured.set_pixel(x,y,c.lightened(amount) if amount>=0 else c.darkened(-amount))
		bases.append(ImageTexture.create_from_image(textured))
	for detail in style.get("variants",[]):
		var picture: Image = Compiler.compile_sprite(recipe(detail),palette).get_image()
		if style.has("detail_key"):
			var clear_color := Color(str(style.detail_key))
			for y in range(16):
				for x in range(16):
					if picture.get_pixel(x,y).is_equal_approx(clear_color):picture.set_pixel(x,y,img.get_pixel(x,y))
		details.append(ImageTexture.create_from_image(picture))
	var allowed: Array[int] = []
	for tile in style.tiles:allowed.append(int(tile))
	return {"base":bases,"details":details,"density":float(style.get("detail_density",.18)),"tiles":allowed,"legacy":style.get("legacy",false)}

func texture(key: String, tile: int, seed_value: int, x: int, y: int) -> Texture2D:
	if not styles.has(key):return null
	var style: Dictionary = styles[key]
	if not tile in style.tiles and not (style.legacy and tile in [0,1,4] and (0 in style.tiles or 1 in style.tiles)):return null
	var roll: int = posmod(hash([seed_value,x,y,key]),1000000)
	if not style.details.is_empty() and roll%1000 < style.density*1000:
		return style.details[(roll/1000)%style.details.size()]
	return style.base[(roll/1000)%style.base.size()]

func display_grid(region: Dictionary) -> Array:
	var grid: Array = region.tiles.duplicate(true)
	var skins: Array = region.get("surfaces",[])
	if skins.is_empty():return grid
	for y in range(grid.size()):
		for x in range(grid[y].size()):
			var key: String = str(skins[y][x])
			if int(grid[y][x]) in [0,1] and styles.has(key):
				var roles: Array = styles[key].tiles
				if 0 in roles:grid[y][x]=0
				elif 1 in roles:grid[y][x]=1
	return grid

func edges(canvas: CanvasItem, grid: Array, x: int, y: int, at: Vector2, extent: float) -> void:
	var tile: int = int(grid[y][x])
	if not tile in [1,2,3]:return
	var ground := Color(str(palette.get("ground","#668855")))
	# Only soften inside the painted tile. Walls retain their full blocked silhouette.
	for side in range(4):
		var offset: Vector2i = [Vector2i.UP,Vector2i.RIGHT,Vector2i.DOWN,Vector2i.LEFT][side]
		var nx: int = x+offset.x
		var ny: int = y+offset.y
		if nx<0 or ny<0 or ny>=grid.size() or nx>=grid[0].size():continue
		var neighbor: int = int(grid[ny][nx])
		if tile==3 and neighbor!=3:
			var ink: Color = Color(str(palette.get("wall","#676770"))).lightened(.24) if side==0 else Color(str(palette.get("shadow","#25252e")))
			var depth: float = 6 if side==2 else 2
			var rect := Rect2(at,Vector2(extent,depth))
			if side==2:rect.position.y+=extent-depth
			if side in [1,3]:rect=Rect2(at+Vector2(extent-depth if side==1 else 0,0),Vector2(depth,extent))
			canvas.draw_rect(rect,ink)
		elif tile in [1,2] and neighbor==0:
			for segment in range(8):
				var depth: float = 1+posmod(hash([x,y,side,segment]),3)
				var pos: Vector2 = at+Vector2(segment*extent/8,0)
				var size: Vector2 = Vector2(extent/8+1,depth)
				if side==2:pos.y+=extent-depth
				if side in [1,3]:
					pos=at+Vector2(extent-depth if side==1 else 0,segment*extent/8)
					size=Vector2(depth,extent/8+1)
				canvas.draw_rect(Rect2(pos,size),ground)
