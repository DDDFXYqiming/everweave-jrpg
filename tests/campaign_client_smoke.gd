extends SceneTree
var main
func _initialize() -> void:_run.call_deferred()
func _run() -> void:
	create_timer(30).timeout.connect(func() -> void:quit(1))
	main=load("res://client/main.tscn").instantiate()
	main.backend_url="http://127.0.0.1:1"
	main.session_token="fixture-only"
	root.add_child(main)
	await process_frame
	var state: Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://userdata/campaign-fixture/snapshot.json"))
	main._accept_snapshot(state)
	main._show_game()
	await process_frame
	assert(not main.hp_bar.visible and not main.mp_bar.visible)
	assert(not main.panel_buttons.inventory.visible)
	assert(main.role_label.text=="邮差")
	assert(main.quest_label.text.contains("失踪"))
	var graph: Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://userdata/campaign-fixture/atlas.json"))
	main.atlas_panel.canvas.set_graph(graph)
	assert(graph.edges.size()==4)
	assert(main.atlas_panel.canvas.path_to("c1_vault").is_empty(),"Route planner ignored a locked link")
	for edge in graph.edges:edge.locked=false
	main.atlas_panel.canvas.set_graph(graph)
	assert(main.atlas_panel.canvas.path_to("c1_vault").size()==3)
	state.game_spec.resources=[{"id":"hp","label":"机体完整度","value":70,"max":90,"display":"bar"},{"id":"ammo","label":"弹药","value":4,"max":8,"display":"number"}]
	state.game_spec.identity="维修员"
	state.version=int(state.version)+1
	main._accept_snapshot(state)
	assert(main.resource_rows.ammo.label.text.contains("弹药"))
	assert(not main.resource_rows.ammo.bar.visible)
	assert(main.stats_label.text.contains("弹药") and not main.stats_label.text.contains("MP"))
	main.queue_free();main=null;await create_timer(.25).timeout
	print("CAMPAIGN_CLIENT_OK flexible_resources=true goals=true loops=true locked_routes=true")
	quit(0)
