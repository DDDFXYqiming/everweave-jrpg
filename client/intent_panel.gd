extends Control
const L = preload("res://client/i18n.gd")
const Icons = preload("res://client/ui_icons.gd")

var main
var panel: PanelContainer
var field: LineEdit
var feedback: Label
var send_button: Button
var http: HTTPRequest
var request_pending: bool = false
var server_status: String = "idle"
var epoch: String = ""
var last_id: String = ""
var proposed_id: String = ""
var proposed_text: String = ""
var proposed_message: String = ""

func build(owner_node: Control) -> void:
	main = owner_node
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	panel = PanelContainer.new()
	add_child(panel)
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.035, 0.065, 0.055, 0.96)
	style.border_color = Color(0.75, 0.66, 0.46, 0.75)
	style.set_border_width_all(2)
	for edge in [SIDE_LEFT, SIDE_TOP, SIDE_RIGHT, SIDE_BOTTOM]: style.set_content_margin(edge, 12)
	panel.add_theme_stylebox_override("panel", style)
	var stack := VBoxContainer.new()
	stack.add_theme_constant_override("separation", 8)
	panel.add_child(stack)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	stack.add_child(row)
	field = LineEdit.new()
	field.max_length = 240
	field.placeholder_text = L.t("你想做什么？")
	field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	field.custom_minimum_size = Vector2(180, 44)
	field.text_submitted.connect(func(_text: String) -> void: _submit())
	field.text_changed.connect(func(_text: String) -> void: _refresh_controls())
	row.add_child(field)
	send_button = main._button(row, "", _submit)
	send_button.icon = Icons.get_icon("send")
	send_button.custom_minimum_size = Vector2(44, 44)
	send_button.tooltip_text = L.t("行动 · Enter")
	var close_button: Button = main._button(row, "", dismiss)
	close_button.icon = Icons.get_icon("close")
	close_button.custom_minimum_size = Vector2(44, 44)
	close_button.tooltip_text = L.t("收起 · Esc")
	feedback = main._label(stack, "", 16, main.MUTED)
	feedback.autowrap_mode = TextServer.AUTOWRAP_OFF
	feedback.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	feedback.max_lines_visible = 1
	http = HTTPRequest.new()
	http.timeout = 10
	add_child(http)
	http.request_completed.connect(_completed)
	resized.connect(_layout)
	hide()
	_layout.call_deferred()

func _layout() -> void:
	if not is_instance_valid(panel): return
	var width: float = minf(740.0, maxf(260.0, size.x - 40.0))
	panel.size.x = width
	panel.position = Vector2((size.x - width) * 0.5, maxf(12.0, size.y - panel.size.y - 72.0))

func toggle() -> void:
	if visible:
		dismiss()
		return
	if not bool(main.state.get("started", false)) or not main.state.get("region") is Dictionary: return
	show()
	_layout()
	field.grab_focus()

func dismiss() -> void:
	hide()
	get_viewport().gui_release_focus()

func _process(_delta: float) -> void:
	if not visible: return
	if request_pending or server_status == "resolving":
		send_button.modulate.a = 0.55 + 0.45 * absf(sin(float(Time.get_ticks_msec()) / 550.0))
	else:
		send_button.modulate.a = 1.0

func update_state(snapshot: Dictionary) -> void:
	var incoming_epoch: String = str(snapshot.get("epoch", ""))
	if incoming_epoch != epoch:
		epoch = incoming_epoch
		field.text = ""
		feedback.text = ""
		last_id = ""
		proposed_id = ""
		proposed_text = ""
		proposed_message = ""
		dismiss()
	var intent: Dictionary = snapshot.get("intent", {})
	server_status = str(intent.get("status", "idle"))
	proposed_id = str(intent.get("id", "")) if server_status == "proposed" else ""
	proposed_text = str(intent.get("text", "")) if server_status == "proposed" else ""
	proposed_message = str(intent.get("message", "")) if server_status == "proposed" else ""
	if server_status != "idle":
		feedback.text = L.t("正在思量…") if server_status == "resolving" else str(intent.get("message", ""))
		feedback.tooltip_text = feedback.text
		feedback.modulate = main.MUTED if server_status in ["resolving", "completed"] else main.GOLD
		var incoming_id: String = str(intent.get("id", ""))
		if incoming_id != last_id and server_status == "completed": field.text = ""
		if server_status not in ["resolving", "proposed"]: last_id = incoming_id
	_refresh_controls()
	_layout.call_deferred()

func _refresh_controls() -> void:
	var busy: bool = request_pending or server_status == "resolving"
	field.editable = not busy
	send_button.disabled = busy or not main.connection_ready or field.text.strip_edges().is_empty()
	var confirmation: bool = not proposed_id.is_empty() and field.text.strip_edges() == proposed_text
	send_button.icon = Icons.get_icon("generation" if busy else ("check" if confirmation else "send"))
	send_button.tooltip_text = L.t("执行 · Enter" if confirmation else "行动 · Enter")
	if server_status == "proposed" and not request_pending:
		feedback.text = proposed_message if confirmation else ""
		feedback.tooltip_text = feedback.text

func _submit() -> void:
	if request_pending or server_status == "resolving" or not main.connection_ready: return
	var text: String = field.text.strip_edges()
	if text.is_empty(): return
	var headers: PackedStringArray = main._headers()
	var confirmation: bool = not proposed_id.is_empty() and text == proposed_text
	var route: String = "/intent/confirm" if confirmation else "/intent"
	var payload: Dictionary = {"id":proposed_id, "epoch":epoch} if confirmation else {"text":text, "epoch":epoch}
	var result: Error = http.request(main.backend_url + route, headers, HTTPClient.METHOD_POST, JSON.stringify(payload))
	if result != OK:
		feedback.text = L.t("行动未发出，请再试一次。")
		return
	request_pending = true
	feedback.text = L.t("正在思量…")
	_refresh_controls()
	_layout.call_deferred()

func _completed(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	request_pending = false
	var response: Dictionary = main._decode(result, code, body)
	if response.has("error"):
		server_status = "error"
		proposed_id = ""
		feedback.text = L.system_text(str(response.error))
		feedback.modulate = main.GOLD
	else:
		main._accept_snapshot(response)
	_refresh_controls()
	_layout.call_deferred()

func _input(event: InputEvent) -> void:
	if visible and event is InputEventKey and event.pressed and event.keycode == KEY_ESCAPE:
		dismiss()
		get_viewport().set_input_as_handled()

func _exit_tree() -> void:
	if is_instance_valid(http): http.cancel_request()
