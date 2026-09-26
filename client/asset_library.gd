extends RefCounted
const L = preload("res://client/i18n.gd")
## Only manifest IDs resolve; model text never becomes a resource path.
static var assets: Dictionary = {}
static var images: Dictionary = {}
static var sounds: Dictionary = {}
static var checked_files: Dictionary = {}
static var last_error: String = ""

static func _asset_path(item: Dictionary) -> String:
	if OS.has_feature("web"):
		return "res://build/web-blobs/" + str(item.sha256) + ".bin"
	return "res://" + str(item.file)

static func _missing_image() -> Image:
	var missing := Image.create(16,16,false,Image.FORMAT_RGBA8)
	missing.fill(Color.MAGENTA)
	return missing

static func entry(id: String, pinned: String = "", kind: String = "") -> Dictionary:
	if assets.is_empty():
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://assets/library/index.json"))
		if parsed is Dictionary: assets = parsed.get("assets",{})
	if not assets.has(id):
		last_error = L.t("素材库缺少：") + id
		push_error(last_error)
		return {}
	var item: Dictionary = assets[id]
	if (not pinned.is_empty() and pinned != str(item.sha256) and not pinned in item.get("legacy_hashes",[])) or (not kind.is_empty() and kind != str(item.kind)):
		last_error = L.t("素材版本或类型不匹配：") + id
		push_error(last_error)
		return {}
	var file: String = str(item.file)
	if not file.begins_with("assets/library/blobs/") or file.contains(".."):
		last_error = L.t("素材索引路径无效。")
		push_error(last_error)
		return {}
	if not checked_files.has(file):
		var path: String = _asset_path(item)
		if not FileAccess.file_exists(path):
			last_error = L.t("素材文件缺失或损坏：") + id
			push_error(last_error)
			return {}
		var data: PackedByteArray = FileAccess.get_file_as_bytes(path)
		if data.is_empty():
			last_error = L.t("素材文件缺失或损坏：") + id
			push_error(last_error)
			return {}
		var hash := HashingContext.new()
		hash.start(HashingContext.HASH_SHA256)
		hash.update(data)
		if hash.finish().hex_encode() != str(item.sha256):
			last_error = L.t("素材文件缺失或损坏：") + id
			push_error(last_error)
			return {}
		checked_files[file] = true
	return item

static func get_image(id: String, pinned: String = "") -> Image:
	var item: Dictionary = entry(id,pinned,"image")
	if item.is_empty(): return _missing_image()
	if not images.has(id):
		var img := Image.new()
		var result: Error = img.load_png_from_buffer(FileAccess.get_file_as_bytes(_asset_path(item)))
		if result != OK or img.is_empty():
			last_error = L.t("素材文件缺失或损坏：") + id
			push_error(last_error)
			return _missing_image()
		img.convert(Image.FORMAT_RGBA8)
		images[id] = img
	return images[id].duplicate()

static func get_audio(id: String, pinned: String = "") -> AudioStream:
	var item: Dictionary = entry(id,pinned)
	if item.is_empty() or not str(item.kind) in ["sfx","music"]: return null
	if not sounds.has(id):
		var stream: AudioStreamOggVorbis = AudioStreamOggVorbis.load_from_buffer(FileAccess.get_file_as_bytes(_asset_path(item))) if OS.has_feature("web") else AudioStreamOggVorbis.load_from_file(_asset_path(item))
		if stream == null:
			last_error = L.t("素材文件缺失或损坏：") + id
			push_error(last_error)
			return null
		sounds[id] = stream
	return sounds[id].duplicate()
