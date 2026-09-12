extends SceneTree
const View = preload("res://client/presentation.gd")
var main

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	create_timer(25).timeout.connect(func() -> void: quit(1))
	main = load("res://client/main.tscn").instantiate()
	main.backend_url = "http://127.0.0.1:1"
	main.session_token = "presentation-test-only"
	root.add_child(main)
	await process_frame
	var fixture: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://tests/fixtures/demo_snapshot.json"))
	var original: Dictionary = fixture.duplicate(true)
	View.inventory(fixture)
	assert(original == fixture)
	assert(View.records(null).is_empty())
	var records := {"journal":["普通文本",{"text":"结构化经历"},null,15]}
	assert(View.history(records) == ["结构化经历","普通文本"])
	var tool := {"id":"r0:needle","name":"补缝针","kind":"tool","quantity":1,"use":{"label":"缝好外套"}}
	var parsed: Dictionary = View.inventory({"inventory":[tool]})[0]
	assert(parsed.can_use and parsed.action_label == "缝好外套")
	assert(not View.inventory({"inventory":[{"id":"r0:key","kind":"key","quantity":1}]})[0].can_use)
	main._accept_snapshot(fixture)
	main._show_game()
	main._toggle_panel("inventory")
	await process_frame
	assert(main.modal_overlay.visible)
	main._inventory_category("tool")
	await process_frame
	var accidental_wait := InputEventKey.new()
	accidental_wait.keycode = KEY_PERIOD
	accidental_wait.pressed = true
	main._unhandled_key_input(accidental_wait)
	assert(not main.action_busy) # Reading the bag cannot advance the game.
	var close_book := InputEventKey.new()
	close_book.keycode = KEY_ESCAPE
	close_book.pressed = true
	main._input(close_book)
	assert(main.local_panel.is_empty())
	main._toggle_panel("journal")
	main._journal_category("threads")
	await process_frame
	main._journal_category("history")
	await process_frame
	main._show_home()
	for i in range(3):
		main._home_tab(i)
		assert(main.home_pages[i].visible)
	assert(root.content_scale_aspect == Window.CONTENT_SCALE_ASPECT_EXPAND)
	main.queue_free()
	main = null
	await create_timer(0.2).timeout
	print("PRESENTATION_OK snapshot_preserved=true optional_fields=true item_actions=true journal_tabs=true expanded_aspect=true")
	quit(0)
