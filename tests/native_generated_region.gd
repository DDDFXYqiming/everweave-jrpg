extends SceneTree
## Opens an existing generated save through the real client and local HTTP bridge.
var main

func _initialize() -> void:
	_run.call_deferred()

func _click(button: Button) -> void:
	await process_frame
	var event := InputEventMouseButton.new()
	event.button_index=MOUSE_BUTTON_LEFT
	event.position=button.get_global_rect().get_center()
	event.pressed=true
	root.push_input(event,true)
	var release:=event.duplicate();release.pressed=false;root.push_input(release,true)
	while main.action_busy:await process_frame
	await process_frame
	assert(main.last_action_error.is_empty(),main.last_action_error)

func _tap(key: int) -> void:
	var event:=InputEventKey.new();event.keycode=key;event.pressed=true;root.push_input(event,true)
	var release:=event.duplicate();release.pressed=false;root.push_input(release,true)
	await process_frame

func _run() -> void:
	create_timer(40).timeout.connect(func() -> void:push_error("Generated region native timeout");quit(1))
	load("res://client/i18n.gd").set_language("zh",false)
	main=load("res://client/main.tscn").instantiate();root.add_child(main)
	while not main.connection_ready:await process_frame
	assert(main.state.started and main.state.region is Dictionary)
	await _click(main.return_button)
	assert(main.game.visible)
	assert(main.world_view.generated.size()>0)
	assert(not main.soundscape.track_signature.is_empty())
	assert(main.task_button.visible and main.atlas_panel!=null)
	assert(int(main.state.director.calls)==0)
	print("NATIVE_GENERATED_REGION_OK name=",main.state.region.name," sprites=",main.world_view.generated.size()," cloud_calls=0")
	main.queue_free();await create_timer(.2).timeout;quit(0)
