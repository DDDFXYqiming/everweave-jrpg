extends SceneTree
## Executed twice against a test-only settings file to verify process restart.
func _initialize() -> void: _run.call_deferred()
func _run() -> void:
	var prefs = root.get_node("AudioPrefs")
	assert(prefs.settings_path.contains("userdata/"),"Use a test-only settings path")
	if "--write" in OS.get_cmdline_user_args():
		prefs.set_muted(true)
		prefs.set_volume("music",.37)
		prefs.set_volume("ambience",.13)
		prefs.set_volume("sfx",.61)
		prefs.set_fullscreen(true)
		prefs.learn("move")
		print("PREFERENCES_WRITTEN")
	else:
		assert(prefs.master_muted and prefs.fullscreen and prefs.learned.has("move"))
		assert(is_equal_approx(prefs.music_volume,.37) and is_equal_approx(prefs.ambience_volume,.13))
		assert(is_equal_approx(prefs.sfx_volume,.61))
		assert(AudioServer.is_bus_mute(AudioServer.get_bus_index("Master")))
		print("PREFERENCES_RESTART_OK muted=true independent_volumes=true fullscreen=true tutorial=true")
	quit(0)
