extends SceneTree
## Real renderer, actual Control hit testing and the local HTTP bridge; no cloud.
var main
var prefs
const OUT = "res://userdata/ui-acceptance"

func _initialize() -> void: _run.call_deferred()

func click(button: Button) -> void:
	await process_frame
	assert(button.is_visible_in_tree(), "Attempted to click a hidden control")
	var e := InputEventMouseButton.new()
	e.button_index = MOUSE_BUTTON_LEFT
	e.position = button.get_global_rect().get_center()
	e.pressed = true
	root.push_input(e,true)
	e = e.duplicate()
	e.pressed = false
	root.push_input(e,true)
	await process_frame
	while main.action_busy: await process_frame

func tap(key: int, ctrl: bool = false, alt: bool = false) -> void:
	var e := InputEventKey.new()
	e.keycode = key
	e.ctrl_pressed = ctrl
	e.alt_pressed = alt
	e.pressed = true
	root.push_input(e,true)
	var release := e.duplicate()
	release.pressed = false
	root.push_input(release,true)
	await process_frame
	while main.action_busy: await process_frame

func capture(name: String) -> void:
	if DisplayServer.get_name() == "headless": return
	await process_frame
	await RenderingServer.frame_post_draw
	var image := root.get_texture().get_image()
	assert(image.get_width() > 100)
	assert(image.save_png(OUT + "/" + name + ".png") == OK)

func _run() -> void:
	create_timer(90).timeout.connect(func() -> void: push_error("UI acceptance timeout");quit(1))
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(OUT))
	prefs = root.get_node("AudioPrefs")
	prefs.set_muted(false)
	load("res://client/i18n.gd").set_language("zh",false)
	main = load("res://client/main.tscn").instantiate()
	root.add_child(main)
	while not main.connection_ready: await process_frame
	assert(main.state.started and main.state.region is Dictionary)
	await click(main.return_button)
	if not main.state.get("ui",{}).is_empty(): await tap(KEY_ESCAPE)
	var before: Dictionary = main.state.player.duplicate(true)
	for resolution in [Vector2i(1280,800),Vector2i(1680,900),Vector2i(1920,1080)]:
		root.size = resolution
		await create_timer(.4).timeout
		assert(main.world_view.size.x >= main.size.x - 50, "HUD still reserves a permanent side column")
		assert(not main.director_label.is_visible_in_tree())
		assert(not main.game.journey_drawer.visible and not main.game.pause_menu.visible)
		assert(main.game.sound_button.get_global_rect().end.x <= main.size.x)
		assert(main.quest_label.max_lines_visible == 1)
		await capture("hud-" + str(resolution.x))
	await tap(KEY_TAB)
	assert(main.game.journey_drawer.visible)
	await capture("journey")
	await tap(KEY_ESCAPE)
	await tap(KEY_D,true)
	assert(main.game.developer_overlay.visible and main.director_label.is_visible_in_tree())
	await capture("diagnostics")
	await tap(KEY_ESCAPE)
	await tap(KEY_ESCAPE)
	assert(main.game.pause_menu.visible)
	await capture("pause")
	await tap(KEY_ESCAPE)
	var icon_on: PackedByteArray = main.game.sound_button.icon.get_image().get_data()
	await click(main.game.sound_button)
	assert(prefs.master_muted and AudioServer.is_bus_mute(AudioServer.get_bus_index("Master")))
	assert(main.game.sound_button.icon.get_image().get_data() != icon_on)
	assert(not main.audio_settings_panel.toggle.button_pressed)
	main._show_home()
	main._home_tab(1)
	await capture("audio-muted")
	await click(main.audio_settings_panel.toggle)
	assert(not prefs.master_muted and main.game.sound_button.button_pressed)
	main.audio_settings_panel.sliders.ambience.value = 13
	assert(is_equal_approx(prefs.ambience_volume,.13))
	assert(not is_equal_approx(prefs.sfx_volume,.13))
	await capture("audio-on")
	prefs.set_muted(true)
	prefs.set_fullscreen(true)
	# A fresh instance reads persisted settings, exactly as a restarted app does.
	var restored = load("res://client/audio_settings.gd").new()
	restored.settings_path = prefs.settings_path
	restored.load_settings()
	assert(restored.master_muted and restored.fullscreen and is_equal_approx(restored.ambience_volume,.13))
	restored.free()
	prefs.set_fullscreen(false)
	prefs.set_muted(false)
	main._change_language(1,false,false)
	await process_frame
	assert(main.audio_settings_panel.toggle.text == "All sound: on")
	assert(main.audio_settings_panel.values.ambience.text == "13%")
	await capture("audio-en")
	main._show_game()
	await tap(KEY_D,true)
	assert(main.game.developer_overlay.visible)
	await capture("diagnostics-en")
	await tap(KEY_ESCAPE)
	assert(main.state.player == before,"Presentation changed authoritative player state")
	assert(main.theme.default_font is FontFile)
	assert(main.title_label.get_theme_font("font") is FontFile)
	assert(main.state.director.calls == 0)
	# Exercise the portable full-screen shortcut itself, not only the stored flag.
	if DisplayServer.get_name() != "headless":
		await tap(KEY_ENTER,false,true)
		assert(root.mode == Window.MODE_FULLSCREEN and prefs.fullscreen)
		await tap(KEY_ENTER,false,true)
		assert(root.mode != Window.MODE_FULLSCREEN and not prefs.fullscreen)
	await capture("hud-en")
	main.queue_free()
	await create_timer(.2).timeout
	print("NATIVE_UI_ACCEPTANCE_OK sizes=1280x800,1680x900,1920x1080 icons_sync=true persistence=true english=true shortcuts=Tab,Ctrl+D,Esc cloud_calls=0")
	quit(0)
