extends SceneTree
const Library = preload("res://client/asset_library.gd")
const Compiler = preload("res://client/visual_compiler.gd")
const Soundscape = preload("res://client/soundscape.gd")

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	create_timer(25).timeout.connect(func() -> void: quit(1))
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
	var bus: int = AudioServer.bus_count
	AudioServer.add_bus()
	AudioServer.set_bus_name(bus,"HybridAcceptance")
	var capture := AudioEffectCapture.new()
	capture.buffer_length = .2
	AudioServer.add_bus_effect(bus,capture)
	for player in sound.music_players+sound.effect_players:player.bus = "HybridAcceptance"
	sound.ambience.bus = "HybridAcceptance"
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
	sound.muted = true
	sound.effects_gain = 0
	await create_timer(.3).timeout
	assert(sound.music_players[sound.current_slot].stream_paused)
	capture.clear_buffer()
	await create_timer(.12).timeout
	var silent: PackedVector2Array = capture.get_buffer(capture.get_frames_available())
	var muted_power: float = 0
	for sample in silent:muted_power += sample.length_squared()
	assert(muted_power<0.00001)
	sound.queue_free()
	await create_timer(.15).timeout
	AudioServer.remove_bus(bus)
	print("HYBRID_AUDIO_OK library_pixels=true composite_pixels=true decoded_audio=true music_transition=true cue_dedup=true synthesis=true mute=true")
	quit(0)
