extends SceneTree
const Terrain = preload("res://client/terrain_materials.gd")
const View = preload("res://client/world_view.gd")

func _initialize() -> void:_run.call_deferred()

func _run() -> void:
	create_timer(20).timeout.connect(func() -> void:quit(1))
	var palette := {"ground":"#84c669","path":"#bbae7a","wall":"#656477","shadow":"#24232f","water":"#5284ab","accent":"#d4a864"}
	var visuals := {"terrain":"grass","style":"material verification","palette":palette,"sprites":{"floor":{"asset":"town_v1_grass","size":[16,16]},"hero":{"asset":"dungeon_v1_adventurer","size":[16,16]}},"scenery":[]}
	var surface = Terrain.new()
	surface.configure(visuals)
	var texture: Texture2D = surface.texture("floor",0,42,3,3)
	assert(texture!=null)
	assert(texture.get_image().get_data()==surface.texture("floor",0,42,3,3).get_image().get_data(),"Sampling changed between frames")
	var colors: Dictionary = {}
	var variants: Dictionary = {}
	for x in range(16):
		var image: Image = surface.texture("floor",0,42,x,3).get_image()
		variants[hash(image.get_data())]=true
		for y in range(16):colors[image.get_pixel(x,y)]=true
	assert(colors.size()>8 and variants.size()>3,"Flat base still suppresses ground variation")
	assert(surface.texture("floor",3,42,3,3)==null,"Grass must not hide a blocked wall")
	visuals.sprites.road={"asset":"town_v1_stone_path","size":[16,16]}
	surface.configure(visuals)
	assert(surface.texture("road",0,42,3,3)!=null,"An old GROUND road lost its surface")
	var stone: Image = surface.styles.road.details[0].get_image()
	for y in range(16):
		for x in range(16):assert(not stone.get_pixel(x,y).is_equal_approx(Color("#84c669")),"Detail left a square of grass on the dirt road")
	var logical: Array = [[0,0,3]]
	var view_grid: Array = surface.display_grid({"tiles":logical,"surfaces":[["floor","road","road"]]})
	assert(view_grid==[[0,1,3]] and logical==[[0,0,3]],"Visual roles rewrote collision data")
	var view = View.new()
	view.size=Vector2(480,320)
	root.add_child(view)
	await process_frame
	var tiles: Array = []
	var surfaces: Array = []
	for y in range(10):
		var row: Array = []
		var skins: Array = []
		for x in range(15):
			row.append(3 if (x in [3,10] and y>=2 and y<=7) or (y in [2,7] and x>=3 and x<=10) else 0)
			skins.append("floor")
		tiles.append(row);surfaces.append(skins)
	tiles[7][6]=1
	var region := {"id":"room","seed":42,"width":15,"height":10,"tiles":tiles,"surfaces":surfaces,"visuals":visuals,"entities":[],"props":[],"biome":"forest","weather":"clear","scene":{"paint":[{"room":[3,2,8,6],"tile":0,"surface":"floor","doors":[[6,7]]}]}}
	view.update_world({"region":region,"player":{"x":6,"y":8},"time":480})
	assert(view.room_floor_keys.has(Vector2i(3,3)))
	assert(not view.room_floor_keys.has(Vector2i(1,1)),"Legacy repair changed an unrelated wall")
	region.surface_version=2
	view.update_world({"region":region,"player":{"x":6,"y":8},"time":480})
	assert(view.room_floor_keys.is_empty())
	view.queue_free()
	await process_frame
	print("TERRAIN_MATERIALS_OK deterministic=true textured=true wall_visibility=true legacy_scope=true")
	quit(0)
