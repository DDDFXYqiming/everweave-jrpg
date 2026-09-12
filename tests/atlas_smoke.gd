extends SceneTree
const Canvas = preload("res://client/atlas_canvas.gd")
func _initialize() -> void:
	_run.call_deferred()
func _run() -> void:
	create_timer(20).timeout.connect(func() -> void: quit(1))
	var canvas = Canvas.new()
	root.add_child(canvas)
	canvas.size = Vector2(900,550)
	await process_frame
	var graph := {"epoch":"atlas-smoke-"+str(Time.get_ticks_usec()),"current":"r0","nodes":[],"edges":[]}
	for i in range(100):
		var id: String = "r"+str(i)
		graph.nodes.append({"id":id,"parent":"r"+str(i-1) if i else "","name":"地点"+str(i),"visited":i<80,"ready":true,"tasks":[]})
		if i:graph.edges.append({"a":"r"+str(i-1),"b":id})
	canvas.set_graph(graph)
	var original: Dictionary = canvas.positions.duplicate()
	assert(canvas.path_to("r99").size()==100)
	canvas.select_place("r99",true)
	assert(not canvas.concealed.has("r99"))
	graph.nodes.append({"id":"new_branch","parent":"r2","name":"新岔路","visited":false,"ready":false,"tasks":[]})
	graph.edges.append({"a":"r2","b":"new_branch"})
	canvas.set_graph(graph)
	for id in original:assert(canvas.positions[id]==original[id])
	assert(canvas.path_to("new_branch")==["r0","r1","r2","new_branch"])
	var before: Vector2 = canvas.pan
	canvas.change_zoom(1.2)
	assert(canvas.pan!=before)
	var saved_pan: Vector2 = canvas.pan
	var saved_zoom: float = canvas.zoom
	var reloaded = Canvas.new()
	root.add_child(reloaded)
	reloaded.size = canvas.size
	reloaded.set_graph(graph)
	assert(reloaded.pan==saved_pan and reloaded.zoom==saved_zoom)
	assert(reloaded.positions==canvas.positions)
	canvas.queue_free()
	reloaded.queue_free()
	await create_timer(.15).timeout
	print("ATLAS_OK stable_layout=true full_graph_search=true local_routes=true persistent_view=true")
	quit(0)
