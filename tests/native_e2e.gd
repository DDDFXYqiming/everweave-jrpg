extends SceneTree
## Real native scene + real authenticated HTTP bridge; isolated save required by runner.
var main
var steps: int = 0

func _initialize() -> void:
	_run.call_deferred()

func _capture(name: String) -> void:
	if DisplayServer.get_name() == "headless": return
	await process_frame
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png("res://userdata/e2e/" + name + ".png")

func _idle() -> void:
	while main.action_busy: await process_frame
	await process_frame
	assert(main.last_action_error.is_empty(), main.last_action_error)

func _act(action: Dictionary) -> void:
	main._send_action(action)
	await _idle()
	steps += 1

func _entity(local_id: String) -> Dictionary:
	for e in main.state.region.entities:
		if str(e.get("local_id", "")) == local_id or str(e.id) == local_id: return e
	assert(false, "Missing test entity: " + local_id)
	return {}

func _walk(e: Dictionary) -> void:
	var r: Dictionary = main.state.region
	var start := Vector2i(int(main.state.player.x), int(main.state.player.y))
	var target := Vector2i(int(e.x), int(e.y))
	var occupied: Dictionary = {}
	for other in r.entities:
		if not other.spent and other.kind != "exit": occupied[Vector2i(int(other.x), int(other.y))] = true
	var queue: Array[Vector2i] = [start]
	var parents: Dictionary = {start:start}
	var end := start
	var found := false
	while not queue.is_empty():
		var pos: Vector2i = queue.pop_front()
		if absi(pos.x - target.x) + absi(pos.y - target.y) == 1:
			end = pos
			found = true
			break
		for delta in [Vector2i.UP, Vector2i.DOWN, Vector2i.LEFT, Vector2i.RIGHT]:
			var next: Vector2i = pos + delta
			if parents.has(next) or occupied.has(next) or next.x < 0 or next.y < 0 or next.x >= int(r.width) or next.y >= int(r.height): continue
			if int(r.tiles[next.y][next.x]) in [2, 3]: continue
			parents[next] = pos
			queue.append(next)
	assert(found, "No traversable route to " + str(e.name))
	var route: Array[Vector2i] = []
	while end != start:
		route.push_front(end)
		end = parents[end]
	for pos in route:
		await _act({"op":"move", "dx":pos.x-int(main.state.player.x), "dy":pos.y-int(main.state.player.y)})
		assert(main.state.battle == null)
	main.world_view.entity_clicked.emit(str(e.id))
	await _idle()

func _button(label: String) -> Button:
	var pending: Array[Node] = [main.modal_stack]
	while not pending.is_empty():
		var node: Node = pending.pop_back()
		if node is Button and node.text == label: return node
		for child in node.get_children(): pending.append(child)
	assert(false, "Missing button: " + label)
	return null

func _run() -> void:
	load("res://client/i18n.gd").set_language("zh",false)
	main = load("res://client/main.tscn").instantiate()
	root.add_child(main)
	while not main.connection_ready: await process_frame
	assert(not main.state.started, "E2E must use an empty isolated save")
	main.mode_select.select(0)
	main.mode_select.item_selected.emit(0)
	await _capture("settings-online")
	main.mode_select.select(2)
	main.mode_select.item_selected.emit(2)
	await _capture("settings-offline")
	main.start_button.pressed.emit()
	await _idle()
	while not main.state.get("region") is Dictionary: await process_frame
	assert(main.game.visible)
	await _capture("world")
	await _walk(_entity("witness"))
	assert(main.state.ui.kind == "dialogue")
	var choice: Dictionary = main.state.ui.choices[0]
	_button(str(choice.text)).pressed.emit()
	await _idle()
	assert(main.state.story_revision == 1)
	await _capture("choice")
	await _act({"op":"close"})
	await _walk(_entity("cache"))
	await _act({"op":"close"})
	main._toggle_panel("inventory")
	assert(main.modal_overlay.visible)
	await _capture("inventory")
	main._toggle_panel("inventory")
	await _walk(_entity("trader"))
	var gold: int = int(main.state.player.gold)
	var item: Dictionary = main.state.ui.goods[0]
	_button("%s  ·  %d G" % [str(item.name),int(item.price)]).pressed.emit()
	await _idle()
	assert(int(main.state.player.gold) == gold - int(item.price))
	await _act({"op":"close"})
	await _walk(_entity("watcher"))
	assert(main.state.battle is Dictionary)
	await _capture("battle")
	for i in range(30):
		if main.state.battle == null: break
		var p: Dictionary = main.state.player
		var move: String = "potion" if int(p.hp)<25 and int(p.inventory.get("potion",0))>0 else ("skill" if int(p.mp)>=5 and main.state.region.rule!="no_magic" else "attack")
		await _act({"op":"combat","move":move})
	assert(main.state.battle == null)
	assert(main.state.ui.title == "战斗胜利")
	await _act({"op":"close"})
	while not bool(main.state.frontier[0].ready): await process_frame
	var original: String = str(main.state.region.id)
	var target: String = str(main.state.frontier[0].id)
	var gate: Dictionary = {}
	for e in main.state.region.entities:
		if e.get("target", "") == target: gate = e
	await _walk(gate)
	assert(main.state.region.id == target)
	await _capture("next-region")
	for e in main.state.region.entities:
		if e.get("target", "") == original: gate = e
	await _walk(gate)
	assert(main.state.region.id == original)
	assert(main.state.director.calls == 0)
	main._show_home()
	assert(main.mode_select.selected == 2)
	var previous_epoch: String = str(main.state.epoch)
	var previous_snapshot: Dictionary = main.state.duplicate(true)
	main.setting_input.text = "极夜雪原上的灯塔世界，我是寻找春天的信使。"
	main.start_button.pressed.emit()
	assert(main.replace_dialog.visible)
	assert(main.state.epoch == previous_epoch)
	await _capture("rebuild-confirmation")
	main.replace_dialog.get_cancel_button().pressed.emit()
	await process_frame
	assert(main.state.epoch == previous_epoch)
	main.start_button.pressed.emit()
	main.replace_dialog.get_ok_button().pressed.emit()
	await _idle()
	assert(main.state.epoch != previous_epoch)
	while not main.state.get("region") is Dictionary: await process_frame
	assert(main.state.setting == "极夜雪原上的灯塔世界，我是寻找春天的信使。")
	assert(main.state.map_count == 1)
	assert(main.state.player.inventory.potion == 3)
	main._accept_snapshot(previous_snapshot)
	assert(main.state.epoch != previous_epoch)
	await _capture("rebuilt-world")
	print("NATIVE_REBUILD_OK cancel_preserved=true fresh_epoch=true stale_ignored=true")
	print("NATIVE_E2E_OK actions=",steps," maps=",main.state.map_count)
	main.queue_free()
	await create_timer(0.15).timeout
	quit(0)
