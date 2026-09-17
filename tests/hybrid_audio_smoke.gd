extends SceneTree
const Library = preload("res://client/asset_library.gd")
const Compiler = preload("res://client/visual_compiler.gd")
const Soundscape = preload("res://client/soundscape.gd")

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	create_timer(25).timeout.connect(func() -> void: quit(1))
	var prefs = root.get_node("AudioPrefs")
	prefs.settings_path = "res://userdata/hybrid-audio-test.cfg"
	prefs.set_muted(false)
	prefs.set_volume("music",.65)
	prefs.set_volume("sfx",.7)
	prefs.set_volume("ambience",.22)
	var palette := {"ground":"#778855","path":"#ddbb88","water":"#336677","wall":"#555566","accent":"#ff0000","shadow":"#111122"}
	var image: Image = Library.get_image("town_v1_grass")
	var pure := Compiler.compile_sprite({"asset":"town_v1_grass","size":[16,16]},palette)
	assert(pure.get_image().get_data()==image.get_data())
	var house: Dictionary = Library.entry("town_v1_blue_house")
	var old_house: Image = Library.get_image("town_v1_blue_house",str(house.legacy_hashes[0]))
	assert(old_house.get_data()==Library.get_image("town_v1_blue_house").get_data())
	var composed := Compiler.compile_sprite({"size":[32,32],"parts":[{"asset":"town_v1_grass","at":[0,16]}],"layers":[["rect",1,1,2,2,"accent"]]},palette)
	assert(composed.get_image().get_pixel(1,1)==Color.RED)
	assert(composed.get_image().get_pixel(0,16)==image.get_pixel(0,0))
	var sound = Soundscape.new()
	root.add_child(sound)
	await process_frame
	# Capture the actual channel mix arriving at Master. The mute flag on Master
	# and zero channel samples together verify the entire playback path.
	var bus: int = AudioServer.get_bus_index("Master")
	var capture := AudioEffectCapture.new()
	capture.buffer_length = .2
	AudioServer.add_bus_effect(bus,capture)
	for player in sound.music_players: assert(player.bus == "Music")
	for player in sound.effect_players: assert(player.bus == "SFX")
	assert(sound.ambience.bus == "Ambience")
	var state := {"epoch":"audio-test","audio_seq":0,"region":{"id":"r0","runtime":{},"audio":{"music":{"explore":{"asset":"music_v1_port_town"},"combat":{"asset":"music_v1_fairy_battles"}}}},"battle":null}
	sound.update_state(state,true)
	await create_timer(.9).timeout
	assert(sound.music_players[sound.current_slot].playing)
	assert(sound.music_players[sound.current_slot].stream.loop)
	assert(sound.music_changes==1)
	sound.update_state(state,true)
	assert(sound.music_changes==1)
	var samples: PackedVector2Array = capture.get_buffer(capture.get_frames_available())
	assert(samples.size()>0,"Audio bus did not produce samples")
	var power: float = 0
	for sample in samples:power += sample.length_squared()
	assert(power>0.000001,"Decoded music is silent")
	state.battle = {"id":"foe"}
	sound.update_state(state,true)
	assert(sound.music_changes==2)
	state.audio_seq = 1
	state.audio_events = [{"seq":1,"region":"r0","sound":{"asset":"rpg_v1_footstep00"}}]
	sound.update_state(state,true)
	sound.update_state(state,true)
	assert(sound.played_effects==1)
	sound.play_cue({"layers":[{"synth":{"wave":"noise","frequency":60,"duration":.1}},{"asset":"rpg_v1_metal_latch","delay_ms":30}]})
	await create_timer(.2).timeout
	assert(sound.played_effects==3)
	var score: AudioStream = sound._stream({"score":{"bpm":120,"voices":[{"wave":"sine","gain":.2,"notes":[[60,1],[67,1]]}]}},true)
	assert(score is AudioStreamWAV and score.data.size()>0 and score.loop_mode==AudioStreamWAV.LOOP_FORWARD)
	state.region.audio.ambience = {"synth":{"wave":"square","frequency":90,"duration":.8},"volume":1.0}
	state.region.audio.cues = {"confirm":{"synth":{"wave":"triangle","frequency":440,"duration":.2}}}
	state.region.audio.bindings = {"ui":"confirm"}
	sound.update_state(state,true)
	await create_timer(.8).timeout
	assert(sound.ambience.playing and sound.ambience_gain <= .02001)
	sound.play_ui()
	assert(sound.effect_players[sound.effect_slot].bus == "UI")
	sound.play_cue({"synth":{"wave":"square","frequency":300,"duration":.4},"delay_ms":400})
	assert(not sound.scheduled.is_empty())
	var before_mute: int = sound.played_effects
	sound.muted = true
	await create_timer(.3).timeout
	assert(AudioServer.is_bus_mute(AudioServer.get_bus_index("Master")))
	assert(sound.scheduled.is_empty())
	sound.play_ui()
	sound.play_cue({"synth":{"wave":"square","frequency":300,"duration":.4}})
	assert(sound.played_effects == before_mute)
	capture.clear_buffer()
	await create_timer(.12).timeout
	var silent: PackedVector2Array = capture.get_buffer(capture.get_frames_available())
	var muted_power: float = 0
	for sample in silent:muted_power += sample.length_squared()
	assert(muted_power<0.00001)
	sound.muted = false
	capture.clear_buffer()
	await create_timer(.2).timeout
	var resumed_power: float = 0
	for sample in capture.get_buffer(capture.get_frames_available()): resumed_power += sample.length_squared()
	assert(resumed_power > .000001)
	assert(sound.played_effects == before_mute,"Muted queued cues replayed on restore")
	# The persistent hum responds to Ambience independently from SFX.
	for player in sound.music_players: player.stop()
	for player in sound.effect_players: player.stop()
	capture.clear_buffer()
	await create_timer(.2).timeout
	var ambience_power: float = 0
	for sample in capture.get_buffer(capture.get_frames_available()): ambience_power += sample.length_squared()
	assert(ambience_power > .000001)
	prefs.set_volume("ambience",0)
	await create_timer(.15).timeout
	capture.clear_buffer()
	await create_timer(.12).timeout
	var no_ambience_power: float = 0
	for sample in capture.get_buffer(capture.get_frames_available()): no_ambience_power += sample.length_squared()
	assert(no_ambience_power < .00001)
	assert(is_equal_approx(prefs.sfx_volume,.7))
	sound.queue_free()
	await create_timer(.15).timeout
	AudioServer.remove_bus_effect(bus,0)
	print("HYBRID_AUDIO_OK library_pixels=true decoded_audio=true master_mute=true delayed_cues_cleared=true ui_bus=true ambience_independent=true power=",power," muted=",muted_power," resumed=",resumed_power," ambience=",ambience_power," ambience_zero=",no_ambience_power)
	quit(0)
