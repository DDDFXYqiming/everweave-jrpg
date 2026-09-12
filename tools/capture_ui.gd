extends SceneTree
## Render an existing read-only snapshot for visual review. No server or actions.
var main
var output: String

func _initialize() -> void:
	_run.call_deferred()

func capture(name: String) -> void:
	await create_timer(.15).timeout
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(output.path_join(name + ".png"))

func _run() -> void:
	create_timer(35).timeout.connect(func() -> void: quit(1))
	var args: PackedStringArray = OS.get_cmdline_user_args()
	assert(args.size() == 2, "snapshot path and output folder required")
	output = args[1]
	DirAccess.make_dir_recursive_absolute(output)
	root.size = Vector2i(1600,900)
	main = load("res://client/main.tscn").instantiate()
	main.backend_url = "http://127.0.0.1:1"
	main.session_token = "ui-capture-only"
	root.add_child(main)
	await process_frame
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	main._accept_snapshot(data)
	main._show_game()
	await capture("world")
	main._toggle_panel("inventory")
	await capture("inventory")
	main._toggle_panel("journal")
	await capture("journal")
	main._journal_category("history")
	await capture("history")
	main._show_home()
	await capture("journey")
	main._home_tab(1)
	await capture("display")
	main._home_tab(2)
	await capture("connection")
	main.queue_free()
	main = null
	await create_timer(.2).timeout
	print("UI_GALLERY_OK cloud_calls=0")
	quit(0)
