extends SceneTree
## Exercises the real Godot UI with snapshots produced by Python gameplay actions.
const Compiler = preload("res://client/visual_compiler.gd")

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	var snapshots = JSON.parse_string(FileAccess.get_file_as_string("res://tests/fixtures/generated_content.json"))
	assert(snapshots is Array and snapshots.size() == 4)
	var main = load("res://client/main.tscn").instantiate()
	main.backend_url = "http://127.0.0.1:1"
	main.session_token = "content-smoke-only"
	root.add_child(main)
	await process_frame
	main._accept_snapshot(snapshots[0])
	main._show_game()
	await process_frame
	assert(main.world_view.region.width == 28 and main.world_view.region.height == 20)
	assert(main.world_view.generated.has("floor"))
	assert(main.world_view.region.surfaces[1][1] == "floor")
	var art: Dictionary = main.world_view.generated
	var frame_a: PackedByteArray = Compiler.texture("npc", art, 0.0).get_image().get_data()
	var frame_b: PackedByteArray = Compiler.texture("npc", art, 0.23).get_image().get_data()
	assert(frame_a != frame_b)
	main._accept_snapshot(snapshots[1])
	await process_frame
	assert(main.state.ui.kind == "actions" and main.modal_overlay.visible)
	assert(main.state.ui.actions[0].label == "校准余光")
	main._accept_snapshot(snapshots[2])
	await process_frame
	var door: Dictionary = {}
	for entity in main.world_view.region.entities:
		if entity.get("local_id", "") == "door": door = entity
	assert(not door.is_empty() and not door.solid and door.sprite == "opened")
	main._accept_snapshot(snapshots[3])
	await process_frame
	assert(main.battle_canvas != null)
	assert(main.state.battle.authored)
	assert(main.state.available_actions[0].label == "逆向共振")
	main.queue_free()
	await create_timer(0.15).timeout
	print("GODOT_CONTENT_SMOKE_OK animated_pixels=true authored_map=true dynamic_actions=true causal_door=true")
	quit(0)
