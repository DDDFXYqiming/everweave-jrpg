extends SceneTree
const L = preload("res://client/i18n.gd")

func _initialize() -> void:_run.call_deferred()

func texts(node: Node) -> Array[String]:
	var result: Array[String] = []
	if node is Label or node is Button:result.append(node.text)
	for child in node.get_children():result.append_array(texts(child))
	return result

func _run() -> void:
	create_timer(35).timeout.connect(func() -> void:quit(1))
	L.set_language("zh",false)
	var main = load("res://client/main.tscn").instantiate()
	main.backend_url="http://127.0.0.1:1"
	main.session_token="i18n-isolated-test"
	root.add_child(main)
	await process_frame
	main.setting_input.text="保留这段既有设定"
	main.mode_select.select(1)
	main._mode_changed(1)
	main.base_input.text="https://example.invalid/api"
	main.model_input.text="my-model"
	main.key_input.text="typed-key-not-a-real-credential"
	main.budget_input.value=7
	main._set_effort("high")
	main._home_tab(2)
	main._change_language(1,false,false)
	await process_frame
	assert(main.language_select.selected==1)
	assert(main.home_page_index==2)
	assert(main.setting_input.text=="保留这段既有设定")
	assert(main.key_input.text=="typed-key-not-a-real-credential")
	assert(main._configuration().max_calls==7 and main._configuration().language=="en")
	assert(main._configuration().base_url=="https://example.invalid/api")
	assert(main._configuration().reasoning_effort=="high")
	assert("New journey" in texts(main.home))
	assert("Current objectives" in texts(main.game))
	assert("Music volume" in texts(main.home))
	var snapshot: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://tests/fixtures/demo_snapshot.json"))
	main._accept_snapshot(snapshot)
	var original: String = JSON.stringify(main.state)
	main._show_game()
	main._toggle_panel("inventory")
	assert("Inventory" in texts(main.modal_stack))
	main._show_home()
	main._change_language(0,false,false)
	await process_frame
	assert(main.language_select.selected==0)
	assert("当前待办" in texts(main.game))
	assert(JSON.stringify(main.state)==original,"Language switch changed the saved world's text or state")
	assert(main._configuration().language=="zh")
	main.queue_free()
	await create_timer(.2).timeout
	print("I18N_OK English=true Chinese=true fields_preserved=true story_unchanged=true")
	quit(0)
