extends RefCounted
## Only framework strings pass through this catalog; authored world text stays intact.
static var language: String = "zh"
static var initialized: bool = false
static var installed: bool = false
static var preference_path: String = "user://ui-language.cfg"

static func initialize() -> void:
	if initialized:return
	var config := ConfigFile.new()
	var value: String = "zh"
	if config.load(preference_path)==OK:value=str(config.get_value("ui","language","zh"))
	var override_value: String = OS.get_environment("EVERWEAVE_UI_LANGUAGE")
	if override_value in ["zh","en"]:value=override_value
	set_language(value,false)

static func set_language(value: String, persist: bool = true) -> void:
	if not installed:
		var entries: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://assets/i18n/en.json"))
		var english := Translation.new()
		english.locale="en"
		for key in entries:english.add_message(str(key),str(entries[key]))
		TranslationServer.add_translation(english)
		installed=true
	language="en" if value=="en" else "zh"
	TranslationServer.set_locale("en" if language=="en" else "zh_CN")
	initialized=true
	if persist:
		var config := ConfigFile.new()
		config.set_value("ui","language",language)
		config.save(preference_path)

static func t(message: String) -> String:
	return str(TranslationServer.translate(message)) if language=="en" else message

static func system_text(message: String) -> String:
	if language!="en":return message
	if message.contains("；"):
		var pieces: Array[String] = []
		for part in message.split("；"):pieces.append(system_text(part))
		return "; ".join(pieces)
	var expression := RegEx.new()
	expression.compile("^需要 (.+) ×([0-9]+)（当前 ([0-9]+)）$")
	var match_value: RegExMatch = expression.search(message)
	if match_value:
		return t("需要 %s ×%s（当前 %s）") % [t(match_value.get_string(1)),match_value.get_string(2),match_value.get_string(3)]
	return t(message)
