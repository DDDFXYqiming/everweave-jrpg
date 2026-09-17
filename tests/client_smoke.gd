extends SceneTree
## Run with the actual engine: godot --headless --path . --script res://tests/client_smoke.gd
## This is not a replacement for native rendering/playtesting.

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	load("res://client/i18n.gd").set_language("zh",false)
	var main = load("res://client/main.tscn").instantiate()
	main.backend_url = "http://127.0.0.1:1"
	main.session_token = "isolated-smoke-test"
	root.add_child(main)
	await process_frame
	await process_frame
	assert(main.home.visible)
	assert(main.mode_select.selected == 3)
	assert(main.online_settings.visible)
	assert(main._configuration().reasoning_effort == "high")
	assert(main._configuration().provider=="chatgpt_subscription")
	assert(main._configuration().model=="gpt-5.6-luna" and main._configuration().api_key=="")
	assert(main._configuration().jev_enabled and main.jev_select.button_pressed)
	main.jev_select.button_pressed=false
	assert(not main._configuration().jev_enabled)
	main.jev_select.button_pressed=true
	assert(not main.key_input.visible)
	assert(main.subscription_button.visible and not main.subscription_button.disabled)
	main._set_effort("max")
	assert(main._configuration().reasoning_effort == "max")
	main.mode_select.select(2)
	main.mode_select.item_selected.emit(2)
	assert(not main.online_settings.visible)
	assert(main._configuration().offline)
	main.mode_select.select(1)
	main.mode_select.item_selected.emit(1)
	assert(main.custom_fields.visible)
	assert(not main._configuration().offline)
	assert(not main._configuration().deepseek_options)
	main._set_effort("default")
	assert(main._configuration().reasoning_effort == "default")
	var snapshot = JSON.parse_string(FileAccess.get_file_as_string("res://tests/fixtures/demo_snapshot.json"))
	assert(snapshot is Dictionary)
	main._accept_snapshot(snapshot)
	main.state.director.provider="codex_subscription"
	main.state.director.mode="live_llm"
	main.state.director.model="gpt-5.6-luna"
	main.state.director.reasoning_effort="high"
	main.state.director.jev_enabled=true
	main.state.director.jev_requests=2
	main.state.director.jev_concerns=1
	main.state.director.active_tasks=[{"kind":"region","target":"r0","name":"测试地区","source":"prefetch","elapsed_seconds":42.0,"phase":"generating","progress":{"stage":"reasoning","output_chars":0}}]
	main._render()
	assert(main.director_label.text.contains("订阅") and main.director_label.text.contains("模型正在推理") and main.director_label.text.contains("Jev 判断 2"))
	var old = {"started":false,"version":0}
	main._accept_snapshot(old)
	assert(main.state.started)
	main._show_game()
	await process_frame
	assert(main.game.visible)
	assert(not main.home.visible)
	assert(main.world_view.region.width == 52)
	main._toggle_panel("inventory")
	await process_frame
	assert(main.modal_overlay.visible)
	main._toggle_panel("inventory")
	await process_frame
	assert(not main.modal_overlay.visible)
	snapshot = snapshot.duplicate(true)
	snapshot.version += 1
	snapshot.battle = {"name": "烟雾守门人", "hp": 35, "max_hp": 35, "monster": "sentinel", "turn": 0, "log": ["客户端战斗冒烟测试"]}
	main._accept_snapshot(snapshot)
	await process_frame
	assert(main.battle_canvas != null)
	snapshot = snapshot.duplicate(true)
	snapshot.version += 1
	snapshot.battle = null
	snapshot.ui = {"kind": "dialogue", "title": "旅人", "lines": ["世界正在继续。"], "choices": []}
	main._accept_snapshot(snapshot)
	await process_frame
	assert(main.modal_overlay.visible)
	var failure_state = snapshot.duplicate(true)
	failure_state.version += 1
	failure_state.director = {"mode":"live_llm", "calls":3, "max_calls":10, "repair_calls":1, "accepted":1, "normalization_count":2,
		"failed_tasks":[{"kind":"region","target":"r_test","name":"待修复的港口","category":"reference","message":"物品引用冲突",
			"issues":[{"path":"region.items[2].id","message":"ambiguous item identity","category":"reference"}]}]}
	main._accept_snapshot(failure_state)
	await process_frame
	assert(main.failure_list.get_child_count() == 1)
	assert(not main.retry_failed_button.disabled)
	assert(main.director_label.text.contains("其中修复 1"))
	assert(main.director_label.text.contains("本地纠正 2"))
	assert(main.failure_list.get_child(0).get_child(0).text.contains("待修复的港口"))
	main.queue_free()
	await create_timer(0.15).timeout
	print("GODOT_CLIENT_SMOKE_OK")
	quit(0)
