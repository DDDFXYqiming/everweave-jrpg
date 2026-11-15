extends RefCounted

const NIGHT_WORDS: Array[String] = ["夜", "深宵", "午夜", "月光", "月下", "星空", "night", "midnight", "moon", "nocturn"]
const DUSK_WORDS: Array[String] = ["黄昏", "暮", "夕", "晨雾", "破晓", "dusk", "twilight", "sunset", "dawn"]
const INDOOR_WORDS: Array[String] = ["室内", "屋内", "殿内", "厅", "堂内", "地下", "地窖", "洞", "窟", "隧道", "墓", "舱", "indoor", "interior", "cellar", "cave", "crypt", "dungeon", "tunnel", "hall"]
const GRIM_WORDS: Array[String] = ["写实", "阴", "冷", "湿", "暗", "悬疑", "废", "grim", "dark", "cold", "gloom", "realistic"]
const WARM_WORDS: Array[String] = ["暖", "灯", "火", "烛", "炉", "warm", "lamp", "fire", "candle", "lantern"]

static func _has(text: String, words: Array[String]) -> bool:
	for word in words:
		if text.contains(word): return true
	return false

static func _clock_night(minutes: float) -> float:
	var hour: float = fmod(minutes, 1440.0) / 60.0
	if hour >= 7.0 and hour <= 17.0: return 0.0
	if hour > 17.0 and hour < 21.0: return (hour - 17.0) / 4.0
	if hour > 4.0 and hour < 7.0: return (7.0 - hour) / 3.0
	return 1.0

static func derive(region: Dictionary, minutes: float) -> Dictionary:
	var visuals: Dictionary = region.get("visuals", {})
	var palette: Dictionary = visuals.get("palette", {})
	var text: String = (str(visuals.get("style", "")) + " " + str(region.get("biome", "")) + " " + str(region.get("name", ""))).to_lower()
	var weather: String = str(region.get("weather", "clear"))
	var indoor: bool = _has(text, INDOOR_WORDS)
	var mood: String = "night" if _has(text, NIGHT_WORDS) else ("dusk" if _has(text, DUSK_WORDS) else "day")
	var clock: float = _clock_night(minutes)
	var night: float = maxf(clock, {"night": 0.72, "dusk": 0.38, "day": 0.0}[mood])
	if indoor: night = maxf(night, 0.55)
	var shadow := Color(str(palette.get("shadow", "#25252e")))
	var accent := Color(str(palette.get("accent", "#d4a864")))
	var night_tint: Color = Color(0.20, 0.24, 0.42).lerp(shadow.lightened(0.25), 0.35)
	var dusk_tint := Color(0.98, 0.76, 0.62)
	var ambient: Color = Color.WHITE.lerp(dusk_tint, clampf(night * 2.0, 0.0, 1.0) * (1.0 - night)).lerp(night_tint, smoothstep(0.25, 1.0, night))
	if indoor: ambient = ambient.lerp(Color(0.34, 0.30, 0.30).lerp(shadow.lightened(0.3), 0.4), 0.55)
	var wet: float = 0.0
	if weather == "rain" and not indoor:
		ambient = ambient * Color(0.80, 0.86, 0.96)
		wet = 1.0
	elif weather == "fog" and not indoor:
		ambient = ambient.lerp(Color(0.72, 0.76, 0.80), 0.25)
	elif weather == "snow" and not indoor:
		ambient = ambient * Color(0.94, 0.98, 1.06)
	ambient.a = 1.0
	var grade := Color(0, 0, 0)
	for key in ["ground", "path", "wall", "shadow"]:
		grade += Color(str(palette.get(key, "#808080")))
	grade = grade / 4.0
	grade.a = 1.0
	var grim: bool = _has(text, GRIM_WORDS)
	return {
		"weather": "clear" if indoor else weather,
		"declared_weather": weather,
		"mood": mood,
		"indoor": indoor,
		"night": snappedf(night, 0.01),
		"clock_night": snappedf(clock, 0.01),
		"ambient": ambient,
		"accent": accent,
		"grade": grade,
		"grade_strength": 0.42 if grim else 0.28,
		"saturation": 0.72 if grim else 0.9,
		"wet": wet,
		"warm_lights": _has(text, WARM_WORDS),
		"lantern": night >= 0.45,
	}

static func summary(value: Dictionary) -> String:
	return JSON.stringify({"weather": value.weather, "declared_weather": value.declared_weather, "mood": value.mood, "indoor": value.indoor, "night": value.night, "clock_night": value.clock_night, "ambient": value.ambient.to_html(false), "grade": value.grade.to_html(false), "warm_lights": value.warm_lights, "lantern": value.lantern})
