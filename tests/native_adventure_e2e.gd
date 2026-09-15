extends "res://tests/native_hybrid_e2e.gd"

func _capture(name: String) -> void:
	if DisplayServer.get_name()=="headless":return
	await process_frame
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png("res://userdata/adventure-e2e/"+name+".png")

func _run() -> void:
	create_timer(60).timeout.connect(func() -> void:push_error("Adventure native timeout: "+phase);quit(1))
	load("res://client/i18n.gd").set_language("zh",false)
	main=load("res://client/main.tscn").instantiate()
	root.add_child(main)
	while not main.connection_ready:await process_frame
	await _click(main.return_button)
	assert(not JSON.stringify(main.state.quests).contains("共同取回信件"))
	await _click(main.task_button)
	assert(main.mission_panel.visible and not main.modal_overlay.visible)
	await _capture("task-panel")
	await _tap(KEY_Q)
	assert(not main.mission_panel.visible)
	await _capture("task-tracker")
	await _tap(KEY_D)
	await _tap(KEY_E)
	await _click(_find("听米拉说"))
	assert(main.state.ui.scene_id=="meeting")
	assert(main.state.ui.portraits.size()==1)
	await _capture("choice-scene")
	await _click(_find("一起调查"))
	assert("listen" in main.state.player.abilities)
	await _tap(KEY_F)
	await _click(_find("集中聆听"))
	assert(main.state.player.resources.focus==2)
	await _tap(KEY_E)
	phase="normal input crosses a real chapter route"
	for i in range(3):await _tap(KEY_W)
	await _tap(KEY_A)
	await _tap(KEY_E)
	assert(main.state.region.id=="c1_station")
	await _tap(KEY_F)
	await _click(_find("集中聆听"))
	assert(main.state.player.resources.focus==1)
	assert(main.state.director.calls==0)
	await _capture("portable-skill")
	main.queue_free();main=null
	await create_timer(.2).timeout
	print("NATIVE_ADVENTURE_E2E_OK scene_choices=true portrait=true earned_skill=true real_travel=true persistent_cost=true cloud_calls=0")
	quit(0)
