extends VBoxContainer
const L = preload("res://client/i18n.gd")
const Icons = preload("res://client/ui_icons.gd")
var toggle: Button
var sliders: Dictionary = {}
var values: Dictionary = {}

func _ready() -> void:
	add_theme_constant_override("separation", 10)
	toggle = Button.new()
	toggle.toggle_mode = true
	toggle.custom_minimum_size.y = 44
	toggle.pressed.connect(func() -> void: AudioPrefs.set_muted(not AudioPrefs.master_muted))
	add_child(toggle)
	for entry in [["music","音乐音量"],["ambience","环境声"],["sfx","音效"],["ui","界面音量"]]:
		var row := HBoxContainer.new()
		add_child(row)
		var label := Label.new()
		label.text = L.t(entry[1])
		label.custom_minimum_size.x = 130
		row.add_child(label)
		var slider := HSlider.new()
		slider.max_value = 100
		slider.step = 1
		slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		slider.custom_minimum_size = Vector2(180, 32)
		slider.value_changed.connect(func(value: float) -> void: AudioPrefs.set_volume(entry[0], value / 100))
		row.add_child(slider)
		sliders[entry[0]] = slider
		var amount := Label.new()
		amount.custom_minimum_size.x = 54
		amount.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		row.add_child(amount)
		values[entry[0]] = amount
	AudioPrefs.changed.connect(sync)
	sync()

func sync() -> void:
	toggle.set_pressed_no_signal(not AudioPrefs.master_muted)
	toggle.text = L.t("全部声音：关闭") if AudioPrefs.master_muted else L.t("全部声音：开启")
	toggle.icon = Icons.get_icon("sound_off" if AudioPrefs.master_muted else "sound_on")
	toggle.tooltip_text = L.t("声音已关闭 · 按 M 恢复") if AudioPrefs.master_muted else L.t("声音开启 · 按 M 静音")
	for channel in sliders:
		var value: float = AudioPrefs.get(channel + "_volume") * 100
		sliders[channel].set_value_no_signal(value)
		values[channel].text = str(roundi(value)) + "%"
