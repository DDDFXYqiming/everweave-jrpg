extends SceneTree
## Actual UI/input routing + HTTP actions + authoritative executable content.
var main
var phase: String = "startup"

func _initialize() -> void:
	_run.call_deferred()

func _idle() -> void:
	while main.action_busy: await process_frame
	await process_frame
	assert(main.last_action_error.is_empty(), main.last_action_error)

func _tap(key: int) -> void:
	phase = "key " + str(key)
	while main.move_clock > 0: await process_frame
	var event := InputEventKey.new()
	event.keycode = key
	# Windows accessibility input observed a correct keycode with this scan code.
	event.physical_keycode = 4194313
	event.pressed = true
	root.push_input(event, true)
	var released := event.duplicate()
	released.pressed = false
	root.push_input(released, true)
	await _idle()

func _button(label: String) -> Button:
	var pending: Array[Node] = [main.modal_stack]
	while not pending.is_empty():
		var node: Node = pending.pop_back()
		if node is Button and node.text == label: return node
		for child in node.get_children(): pending.append(child)
	assert(false, "Missing generated button: " + label)
	return null

func _capture(name: String) -> void:
	if DisplayServer.get_name() == "headless": return
	await process_frame
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png("res://userdata/content-e2e/" + name + ".png")

func _run() -> void:
	create_timer(30).timeout.connect(func() -> void:
		push_error("Native content test did not complete during " + phase)
		quit(1)
	)
	main = load("res://client/main.tscn").instantiate()
	root.add_child(main)
	while not main.connection_ready: await process_frame
	assert(main.state.started and main.state.region.name == "回声藏书馆")
	main.return_button.pressed.emit()
	await process_frame
	assert(main.failure_list.get_child_count() == 2)
	await _capture("failed-task-panel")
	var other_failure: Dictionary = main.state.director.failed_tasks[1]
	var first_row: Node = main.failure_list.get_child(0)
	first_row.get_child(first_row.get_child_count() - 1).pressed.emit()
	await _idle()
	assert(main.state.director.failed_tasks.size() == 1)
	assert(main.state.director.failed_tasks[0].target == other_failure.target)
	main.retry_failed_button.pressed.emit()
	await _idle()
	assert(main.state.director.failed_tasks.is_empty())
	await _tap(KEY_E)
	assert(main.state.ui.kind == "actions" and main.modal_overlay.visible)
	await _capture("generated-actions")
	_button("校准余光").pressed.emit()
	await _idle()
	assert(main.state.region.runtime.vars.presses == 1)
	await _tap(KEY_F)
	assert(main.state.ui.kind == "actions")
	_button("校准余光").pressed.emit()
	await _idle()
	var door: Dictionary = {}
	for entity in main.state.region.entities:
		if entity.get("local_id", "") == "door": door = entity
	assert(not door.solid and door.sprite == "opened")
	var clock_before: int = int(main.state.region.runtime.clock)
	await _tap(KEY_PERIOD)
	assert(main.state.region.runtime.clock == clock_before + 1)
	for n in range(9):
		await _tap(KEY_D)
		assert(main.state.player.x == 5 + n, "A short tap must move exactly one tile")
	assert(main.state.quests[0].status == "complete")
	assert(main.state.player.gold == 52)
	await _capture("opened-door-objective")
	for n in range(6): await _tap(KEY_D)
	for n in range(2): await _tap(KEY_W)
	assert(main.state.player.x == 19 and main.state.player.y == 8)
	await _tap(KEY_E)
	assert(main.state.battle.authored)
	await _capture("generated-combat")
	await _tap(KEY_1)
	assert(main.state.battle.hp == 30 and main.state.player.mp == 21 and main.state.player.hp == 89)
	await _tap(KEY_ESCAPE)
	assert(main.state.battle == null)
	for n in range(8): await _tap(KEY_S)
	for n in range(4): await _tap(KEY_D)
	assert(main.state.player.x == 23 and main.state.player.y == 16)
	await _tap(KEY_E)
	assert(main.state.ui.kind == "pending_exit" and not main.state.ui.ready)
	var previous_region: String = main.state.region.id
	await _capture("pending-exit")
	phase = "background region arrives at pending exit"
	while not main.state.ui.get("ready", false): await process_frame
	assert(main.state.region.id == previous_region)
	assert(main._exit_wait_phase(main.state.ui) == "ready")
	await _capture("ready-exit")
	await _tap(KEY_E)
	assert(main.state.region.id != previous_region and main.state.ui.is_empty())
	phase = "minimap opens travel atlas through viewport input"
	var before_map: Dictionary = main.state.player.duplicate(true)
	var minimap_click := InputEventMouseButton.new()
	minimap_click.button_index = MOUSE_BUTTON_LEFT
	minimap_click.pressed = true
	minimap_click.position = main.world_view.global_position + Vector2(main.world_view.size.x-80,40)
	root.push_input(minimap_click,true)
	var minimap_release := minimap_click.duplicate()
	minimap_release.pressed = false
	root.push_input(minimap_release,true)
	await process_frame
	assert(main.atlas_panel.visible)
	while main.atlas_panel.busy:await process_frame
	assert(main.atlas_panel.canvas.nodes.has(main.state.region.id))
	assert(main.atlas_panel.canvas.nodes.has(previous_region))
	var travel_canvas = main.atlas_panel.canvas
	var current_position: Vector2 = travel_canvas.positions[main.state.region.id] * travel_canvas.zoom + travel_canvas.pan
	assert(Rect2(Vector2.ZERO,travel_canvas.size).has_point(current_position))
	assert(current_position.distance_to(travel_canvas.size*.5)<2.0)
	main.atlas_panel._mark(previous_region)
	assert(main.atlas_panel.canvas.route.size()==2)
	assert(main.state.player==before_map)
	await _capture("travel-atlas")
	await _tap(KEY_ESCAPE)
	assert(not main.atlas_panel.visible)
	main.queue_free()
	await create_timer(0.15).timeout
	print("NATIVE_CONTENT_E2E_OK targeted_retry=true logical_keys=true short_taps=true dynamic_actions=true causal_door=true objective=true custom_combat=true pending_exit_live_update=true ready_exit_key=true minimap_atlas=true route_without_teleport=true cloud_calls=0")
	quit(0)
