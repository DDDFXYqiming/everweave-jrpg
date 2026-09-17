extends Node
## Music, ambience and bounded cue playback from committed game data.
const Library = preload("res://client/asset_library.gd")
const SAMPLE_RATE: int = 16000
var music_players: Array[AudioStreamPlayer] = []
var effect_players: Array[AudioStreamPlayer] = []
var ambience: AudioStreamPlayer
var generated: Dictionary = {}
var scheduled: Array[Dictionary] = []
var music_gain: float:
	get: return get_node("/root/AudioPrefs").music_volume
	set(value): get_node("/root/AudioPrefs").set_volume("music", value)
var effects_gain: float:
	get: return get_node("/root/AudioPrefs").sfx_volume
	set(value): get_node("/root/AudioPrefs").set_volume("sfx", value)
var muted: bool:
	get: return get_node("/root/AudioPrefs").master_muted
	set(value): get_node("/root/AudioPrefs").set_muted(value)
var current_slot: int = 0
var blend: float = 1
var gains: Array[float] = [0.0,0.0]
var track_signature: String = ""
var ambience_signature: String = ""
var epoch: String = ""
var last_sequence: int = 0
var played_effects: int = 0
var music_changes: int = 0
var effect_slot: int = 0
var effect_gains: Array[float] = []
var current_audio: Dictionary = {}
var ambience_gain: float = 0
var ambience_target_gain: float = 0
var pending_ambience: Dictionary = {}
var ambience_switch_pending: bool = false

func _ready() -> void:
	for i in range(2):
		var player := AudioStreamPlayer.new()
		player.bus = "Music"
		add_child(player)
		music_players.append(player)
	for i in range(8):
		var player := AudioStreamPlayer.new()
		player.bus = "SFX"
		add_child(player)
		effect_players.append(player)
		effect_gains.append(0)
	ambience = AudioStreamPlayer.new()
	ambience.bus = "Ambience"
	add_child(ambience)
	get_node("/root/AudioPrefs").changed.connect(_preferences_changed)

func _preferences_changed() -> void:
	if not muted: return
	scheduled.clear()
	for player in effect_players: player.stop()

func _process(delta: float) -> void:
	blend = minf(1,blend+delta/.7)
	for i in range(2):
		var weight: float = blend if i == current_slot else 1-blend
		music_players[i].volume_db = linear_to_db(maxf(.00001,gains[i]*weight))
		if i != current_slot and blend >= 1: music_players[i].stop()
	# Half-second fade out + half-second fade in; generated sustained gain is capped.
	ambience_gain = move_toward(ambience_gain, ambience_target_gain, delta * .04)
	if ambience_switch_pending and ambience_gain <= .00001:
		ambience.stop()
		ambience_switch_pending = false
		if not pending_ambience.is_empty():
			ambience.stream = _stream(pending_ambience, true)
			ambience.pitch_scale = float(pending_ambience.get("pitch", 1))
			ambience_target_gain = minf(.25, float(pending_ambience.get("volume", .3))) * .08
			if ambience.stream: ambience.play()
	ambience.volume_db = linear_to_db(maxf(.00001,ambience_gain))
	for i in range(effect_players.size()):effect_players[i].volume_db = linear_to_db(maxf(.00001,effect_gains[i]))
	var now: int = Time.get_ticks_msec()
	while not scheduled.is_empty() and int(scheduled[0].due) <= now:
		var entry: Dictionary = scheduled.pop_front()
		_play_effect(entry.spec,entry.gain,entry.pitch,entry.bus)

func _stream(spec: Dictionary, looping: bool = false) -> AudioStream:
	looping = looping and bool(spec.get("loop",true))
	var stream: AudioStream
	if spec.has("asset"):
		stream = Library.get_audio(str(spec.asset),str(spec.get("asset_hash","")))
	elif spec.has("score") or spec.has("synth"):
		var key: String = JSON.stringify(spec)
		if not generated.has(key):
			if generated.size()>=32:generated.clear()
			generated[key] = _synthesize(spec)
		stream = generated[key].duplicate()
	elif spec.get("legacy",false):stream = preload("res://assets/wander.wav").duplicate()
	if stream is AudioStreamOggVorbis:
		stream.loop = looping
		if spec.has("asset"):stream.loop_offset = float(Library.entry(str(spec.asset)).get("loop_start",0))
	elif stream is AudioStreamWAV:
		stream.loop_mode = AudioStreamWAV.LOOP_FORWARD if looping else AudioStreamWAV.LOOP_DISABLED
		stream.loop_begin = 0
		stream.loop_end = int(stream.get_length()*stream.mix_rate)
	return stream

func _synthesize(spec: Dictionary) -> AudioStreamWAV:
	var voices: Array = []
	var bpm: float = 120
	var duration: float = 0
	if spec.has("score"):
		bpm = float(spec.score.bpm)
		voices = spec.score.voices
		for voice in voices:
			var length: float = 0
			for note in voice.notes:length += float(note[1])*60/bpm
			duration = maxf(duration,length)
	else:
		duration = float(spec.synth.duration)
		voices = [{"wave":spec.synth.wave,"gain":.5,"frequency":spec.synth.frequency,"notes":[[60,duration*bpm/60]]}]
	var count: int = mini(SAMPLE_RATE*16,maxi(1,ceili(duration*SAMPLE_RATE)))
	var samples := PackedFloat32Array()
	samples.resize(count)
	var rng := RandomNumberGenerator.new()
	rng.seed = JSON.stringify(spec).hash()
	for voice in voices:
		var cursor: float = 0
		for note in voice.notes:
			var length: float = float(note[1])*60/bpm
			var frequency: float = float(voice.get("frequency",440.0*pow(2,(float(note[0])-69)/12.0)))
			var start: int = int(cursor*SAMPLE_RATE)
			var end: int = mini(count,int((cursor+length)*SAMPLE_RATE))
			if int(note[0]) != 0:
				for i in range(start,end):
					var t: float = float(i-start)/SAMPLE_RATE
					var phase: float = fposmod(t*frequency,1)
					var wave: float = sin(phase*TAU)
					match str(voice.wave):
						"triangle":wave = 1-4*absf(phase-.5)
						"square":wave = 1 if phase < .5 else -1
						"noise":wave = rng.randf_range(-1,1)
					var envelope: float = clampf(minf(t/.012,(length-t)/.04),0,1)
					samples[i] += wave * float(voice.get("gain",.15)) * envelope
			cursor += length
	var bytes := PackedByteArray()
	bytes.resize(count*2)
	for i in range(count):
		var value: int = int(clampf(samples[i],-.95,.95)*32767)
		bytes[i*2] = value & 255
		bytes[i*2+1] = (value >> 8) & 255
	var stream := AudioStreamWAV.new()
	stream.format = AudioStreamWAV.FORMAT_16_BITS
	stream.mix_rate = SAMPLE_RATE
	stream.stereo = false
	stream.data = bytes
	return stream

func update_state(state: Dictionary, active: bool) -> void:
	var next_epoch: String = str(state.get("epoch",""))
	if next_epoch != epoch:
		epoch = next_epoch
		last_sequence = int(state.get("audio_seq",0))
		track_signature = ""
		ambience_signature = ""
		scheduled.clear()
		for player in music_players+effect_players:player.stop()
		ambience.stop()
		ambience_gain = 0
		ambience_target_gain = 0
		ambience_switch_pending = false
	var region: Dictionary = state.get("region",{}) if state.get("region") is Dictionary else {}
	current_audio = region.get("audio",{})
	for event in state.get("audio_events",[]):
		if int(event.seq) <= last_sequence:continue
		last_sequence = int(event.seq)
		if active and str(event.region) == str(region.get("id","")):play_cue(event.sound)
	if not active or region.is_empty():return
	var music: Dictionary = current_audio.get("music",{})
	var cue: String = str(region.get("runtime",{}).get("audio_music",""))
	if cue.is_empty():cue = "combat" if state.get("battle") is Dictionary and music.has("combat") else "explore"
	var score_cue: Dictionary = current_audio.get("cues",{}).get(cue,{})
	var source: Dictionary = music.get(cue,score_cue if score_cue.has("score") else {"legacy":true})
	var signature: String = JSON.stringify(source)
	if signature != track_signature:
		track_signature = signature
		var next: int = 1-current_slot
		var stream: AudioStream = _stream(source,true)
		if stream != null:
			music_players[next].stream = stream
			music_players[next].pitch_scale = float(source.get("pitch",1))
			music_players[next].volume_db = -80
			var base_gain: float = db_to_linear(float(Library.entry(str(source.asset)).get("gain_db",-14))) if source.has("asset") else .2
			gains[next] = float(source.get("volume",1))*minf(.3,base_gain)
			music_players[next].play()
			current_slot = next
			blend = 0
			music_changes += 1
	var background: Dictionary = current_audio.get("ambience",{})
	var background_signature: String = JSON.stringify(background)
	if background_signature != ambience_signature:
		ambience_signature = background_signature
		pending_ambience = background
		ambience_target_gain = 0
		ambience_switch_pending = true

func play_cue(spec: Dictionary, gain: float = 1, pitch: float = 1, delay: float = 0, bus: String = "SFX") -> void:
	if muted: return
	gain *= float(spec.get("volume",.65))
	pitch *= float(spec.get("pitch",1))
	delay += float(spec.get("delay_ms",0))
	if spec.has("layers"):
		for layer in spec.layers:play_cue(layer,gain,pitch,delay,bus)
		return
	if delay > 0:
		if scheduled.size()>=16:return
		scheduled.append({"due":Time.get_ticks_msec()+int(delay),"spec":spec,"gain":gain,"pitch":pitch,"bus":bus})
		scheduled.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:return a.due < b.due)
	else:_play_effect(spec,gain,pitch,bus)

func _play_effect(spec: Dictionary, gain: float, pitch: float, bus: String = "SFX") -> void:
	if muted or (get_node("/root/AudioPrefs").ui_volume if bus == "UI" else effects_gain) <= 0:return
	var stream: AudioStream = _stream(spec)
	if stream == null:return
	effect_slot = (effect_slot+1)%effect_players.size()
	var player: AudioStreamPlayer = effect_players[effect_slot]
	player.bus = bus
	player.stream = stream
	player.pitch_scale = clampf(pitch,.25,4)
	var base_gain: float = db_to_linear(float(Library.entry(str(spec.asset)).get("gain_db",-10)))*.25 if spec.has("asset") else .08
	effect_gains[effect_slot] = gain*minf(.08,base_gain)
	player.volume_db = linear_to_db(maxf(.00001,effect_gains[effect_slot]))
	player.play()
	played_effects += 1

func play_ui() -> void:
	var cue: String = str(current_audio.get("bindings",{}).get("ui",""))
	if not cue.is_empty():play_cue(current_audio.cues[cue],1,1,0,"UI")

func _exit_tree() -> void:
	for player in music_players+effect_players:player.stop()
	if is_instance_valid(ambience):ambience.stop()
