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
	assert(main._configuration().model=="gpt-6-luna" and main._configuration().api_key=="")
	assert(main._configuration().jev_enabled and main.jev_select.button_pressed)
	main.jev_select.button_pressed=false
	assert(not main._configuration().jev_enabled)
	main.jev_select.button_pressed=true
	assert(not main.key_input.visible)
	assert(main.subscription_button.visible and not main.subscription_button.disabled)
	main._set_effort("max")
	assert(main._configuration().reasoning_effort == "max")
	for effort in ["none","low","medium","high","xhigh","max"]:
		main._set_effort(effort)
		assert(main._configuration().reasoning_effort==effort)
	main._set_luna_model("gpt-5.6-luna")
	assert(main._configuration().model=="gpt-5.6-luna")
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
	var old_instance: Dictionary = snapshot.duplicate(true)
	old_instance.instance_id="old-instance"
	old_instance.snapshot_sequence=100
	main.service_connection.expected_instance_id="old-instance"
	main._accept_snapshot(old_instance)
	var restarted: Dictionary = old_instance.duplicate(true)
	restarted.instance_id="new-instance"
	restarted.snapshot_sequence=1
	restarted.version+=1
	main.service_connection.discovered({"url":"http://127.0.0.1:2","token":"test","instance_id":"new-instance"})
	main._accept_snapshot(restarted)
	assert(main.state.instance_id=="new-instance" and int(main.state.snapshot_sequence)==1)
	var late_old: Dictionary = old_instance.duplicate(true)
	late_old.snapshot_sequence=101
	late_old.title="迟到旧快照"
	main._accept_snapshot(late_old)
	assert(main.state.instance_id=="new-instance" and main.state.title!="迟到旧快照")
	var version_before_blocked_action: int = int(main.state.version)
	main.connection_ready=false
	main.service_connection.disconnected=true
	main._post("/action",{"op":"move","dx":1,"dy":0})
	assert(not main.action_busy and int(main.state.version)==version_before_blocked_action)
	main.connection_ready=true
	main.service_connection.disconnected=false
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
