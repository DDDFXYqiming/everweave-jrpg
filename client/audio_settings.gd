extends Node
## One persistent player preference source. Saves contain no model credentials.
signal changed
var master_muted: bool = false
var music_volume: float = .65
var ambience_volume: float = .22
var sfx_volume: float = .7
var ui_volume: float = .55
var fullscreen: bool = false
var learned: Dictionary = {}
var settings_path: String = "user://settings.cfg"
const BUSES := {"music":"Music", "ambience":"Ambience", "sfx":"SFX", "ui":"UI"}

func _ready() -> void:
	var override_path := OS.get_environment("EVERWEAVE_SETTINGS_PATH")
	if not override_path.is_empty(): settings_path = override_path
	load_settings()
	apply()

func load_settings() -> void:
	var config := ConfigFile.new()
	if config.load(settings_path) != OK: return
	master_muted = bool(config.get_value("audio", "master_muted", false))
	for channel in BUSES:
		var value: Variant = config.get_value("audio", channel + "_volume", get(channel + "_volume"))
		if (value is float or value is int) and is_finite(float(value)):
			set(channel + "_volume", clampf(float(value), 0, 1))
	fullscreen = bool(config.get_value("display", "fullscreen", false))
	var stored: Variant = config.get_value("tutorial", "learned", {})
	learned = stored if stored is Dictionary else {}

func save_settings() -> void:
	var config := ConfigFile.new()
	config.set_value("audio", "master_muted", master_muted)
	for channel in BUSES: config.set_value("audio", channel + "_volume", get(channel + "_volume"))
	config.set_value("display", "fullscreen", fullscreen)
	config.set_value("tutorial", "learned", learned)
	if config.save(settings_path) != OK: push_warning("Could not save player settings")

func apply() -> void:
	AudioServer.set_bus_mute(AudioServer.get_bus_index("Master"), master_muted)
	for channel in BUSES:
		var index := AudioServer.get_bus_index(BUSES[channel])
		if index < 0: continue
		var value: float = get(channel + "_volume")
		# Also silence channel buses, so effects/taps upstream of Master are quiet.
		AudioServer.set_bus_mute(index, master_muted or value <= 0)
		AudioServer.set_bus_volume_db(index, linear_to_db(maxf(.00001, value)))
	changed.emit()

func set_muted(value: bool) -> void:
	master_muted = value
	apply()
	save_settings()

func set_volume(channel: String, value: float) -> void:
	if not BUSES.has(channel) or not is_finite(value): return
	set(channel + "_volume", clampf(value, 0, 1))
	apply()
	save_settings()

func set_fullscreen(value: bool) -> void:
	fullscreen = value
	save_settings()

func learn(action: String) -> void:
	if learned.has(action): return
	learned[action] = true
	save_settings()
