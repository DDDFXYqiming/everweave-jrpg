extends SceneTree
var main
var phase: String = "start"

func _initialize() -> void:
	_run.call_deferred()
func _idle() -> void:
	while main.action_busy:await process_frame
	await process_frame
	assert(main.last_action_error.is_empty(),main.last_action_error)
func _tap(key: int) -> void:
	while main.move_clock>0:await process_frame
	var event := InputEventKey.new()
	event.keycode = key
	event.pressed = true
	root.push_input(event,true)
	var release := event.duplicate()
	release.pressed = false
	root.push_input(release,true)
	await _idle()
func _find(label: String) -> Button:
	var queue: Array[Node] = [main.modal_stack]
	while not queue.is_empty():
		var node: Node = queue.pop_front()
		if node is Button and node.text==label:return node
		queue.append_array(node.get_children())
	assert(false,"Missing button: "+label)
	return null
func _click(button: Button) -> void:
	await process_frame
	var event := InputEventMouseButton.new()
	event.button_index = MOUSE_BUTTON_LEFT
	event.position = button.get_global_rect().get_center()
	event.pressed = true
	root.push_input(event,true)
	var release := event.duplicate()
	release.pressed = false
	root.push_input(release,true)
	await _idle()
func _capture(name: String) -> void:
	if DisplayServer.get_name()=="headless":return
	await process_frame
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png("res://userdata/hybrid-e2e/"+name+".png")
func _run() -> void:
	create_timer(40).timeout.connect(func() -> void:
		push_error("Hybrid native timeout: "+phase)
		quit(1)
	)
	main = load("res://client/main.tscn").instantiate()
	root.add_child(main)
	while not main.connection_ready:await process_frame
	await _click(main.return_button)
	assert(main.game.visible)
	assert(main.state.region.module_sources.size()==2)
	assert(main.world_view.generated.has("hero"))
	await _capture("hybrid-world")
	phase = "module button hit through real viewport"
	await _tap(KEY_E)
	await _click(_find("拨开门闩"))
	var door: Dictionary = {}
	for e in main.state.region.entities:
		if e.get("local_id")=="door":door=e
	assert(not door.solid and door.sprite=="opened")
	assert(main.soundscape.played_effects>0)
	await _tap(KEY_E)
	await _click(_find("校准余光"))
	await _tap(KEY_E)
	await _click(_find("校准余光"))
	for i in range(15):await _tap(KEY_D)
	for i in range(2):await _tap(KEY_W)
	assert(main.state.player.x==19 and main.state.player.y==8)
	assert(main.state.quests[0].status=="complete")
	phase = "module combat and music"
	await _tap(KEY_E)
	assert(main.state.battle.authored)
	assert(main.soundscape.track_signature.contains("fairy_battles"))
	await _capture("hybrid-combat")
	await _click(_find("2 余光震荡"))
	assert(main.state.battle.hp==23 and main.state.player.mp==21)
	await _tap(KEY_ESCAPE)
	assert(main.state.battle==null)
	assert(main.soundscape.track_signature.contains("peaceful_ville"))
	assert(main.state.director.calls==0)
	main.queue_free()
	main = null
	await create_timer(.2).timeout
	print("NATIVE_HYBRID_E2E_OK actual_button_hits=true library_world=true module_door=true original_rule=true module_combat=true music_switch=true sound_events=true cloud_calls=0")
	quit(0)
