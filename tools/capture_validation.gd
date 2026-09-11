extends SceneTree
## Render the saved validation snapshot using the actual native client.

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	var snapshot_path := "res://userdata/live-validation/snapshot.json"
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--snapshot="): snapshot_path = arg.trim_prefix("--snapshot=")
	var main = load("res://client/main.tscn").instantiate()
	main.backend_url = "http://127.0.0.1:1"
	main.session_token = "isolated-render"
	root.add_child(main)
	await process_frame
	var snapshot = JSON.parse_string(FileAccess.get_file_as_string(snapshot_path))
	assert(snapshot is Dictionary)
	main._accept_snapshot(snapshot)
	main._show_game()
	await create_timer(1.0).timeout
	await RenderingServer.frame_post_draw
	var result = root.get_texture().get_image().save_png(snapshot_path.get_base_dir().path_join("native.png"))
	assert(result == OK)
	print("NATIVE_RENDER_OK")
	main.queue_free()
	await create_timer(0.15).timeout
	quit(0)
