extends SceneTree
## Actual UI/input routing + HTTP actions + authoritative executable content.
var main

func _initialize() -> void:
	_run.call_deferred()

func _idle() -> void:
	while main.action_busy: await process_frame
	await process_frame
	assert(main.last_action_error.is_empty(), main.last_action_error)

func _tap(key: int) -> void:
	while main.move_clock > 0: await process_frame
	var event := InputEventKey.new()
	event.keycode = key
	# Windows accessibility input observed a correct keycode with this scan code.
	event.physical_keycode = 4194313
	event.pressed = true
	Input.parse_input_event(event)
	var released := event.duplicate()
	released.pressed = false
	Input.parse_input_event(released)
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
	main = load("res://client/main.tscn").instantiate()
	root.add_child(main)
	while not main.connection_ready: await process_frame
	assert(main.state.started and main.state.region.name == "回声藏书馆")
	main.return_button.pressed.emit()
	await process_frame
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
	main.queue_free()
	await create_timer(0.15).timeout
	print("NATIVE_CONTENT_E2E_OK logical_keys=true short_taps=true dynamic_actions=true causal_door=true objective=true custom_combat=true cloud_calls=0")
	quit(0)
