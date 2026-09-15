extends "res://tests/native_hybrid_e2e.gd"

func _run() -> void:
	create_timer(45).timeout.connect(func() -> void:push_error("Threat native timeout");quit(1))
	load("res://client/i18n.gd").set_language("zh",false)
	main=load("res://client/main.tscn").instantiate()
	root.add_child(main)
	while not main.connection_ready:await process_frame
	await _click(main.return_button)
	await _tap(KEY_S)
	await _tap(KEY_D)
	for i in range(12):
		if main.state.battle is Dictionary:break
		await _tap(KEY_PERIOD)
	assert(main.state.battle is Dictionary,"Enemy never approached/initiated combat")
	assert(main.state.battle.name=="巡逻守卫")
	var foe: Dictionary={}
	for e in main.state.region.entities:
		if e.get("local_id")=="guard":foe=e
	assert(foe.alerted and [foe.x,foe.y]!=[12,7])
	var health: int=int(main.state.player.hp)
	await _tap(KEY_1)
	assert(main.state.battle.hp==8 and main.state.player.hp==health-2)
	await _tap(KEY_ESCAPE)
	assert(not main.state.battle is Dictionary)
	await _tap(KEY_PERIOD)
	assert(not main.state.battle is Dictionary,"Retreat immediately restarted the encounter")
	assert(main.state.director.calls==0)
	main.queue_free();main=null;await create_timer(.2).timeout
	print("NATIVE_THREAT_E2E_OK pursuit=true footprint=true automatic_battle=true real_turn=true retreat=true cloud_calls=0")
	quit(0)
