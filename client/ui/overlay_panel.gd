extends Control
signal closed
@onready var panel: PanelContainer = $Panel
@onready var body: VBoxContainer = $Panel/Scroll/Body

func _ready() -> void:
	$Dim.gui_input.connect(func(event: InputEvent) -> void:
		if event is InputEventMouseButton and event.pressed: closed.emit()
	)

func heading(text: String) -> void:
	var row := HBoxContainer.new()
	body.add_child(row)
	var label := Label.new()
	label.text = text
	label.add_theme_font_override("font",preload("res://assets/fonts/FusionPixel.ttf"))
	label.add_theme_font_size_override("font_size",24)
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(label)
	var close := Button.new()
	close.icon = preload("res://client/ui_icons.gd").get_icon("close")
	close.tooltip_text = preload("res://client/i18n.gd").t("收起 · Esc")
	close.pressed.connect(func() -> void: closed.emit())
	row.add_child(close)
