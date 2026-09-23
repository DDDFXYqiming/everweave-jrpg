extends RefCounted
## 只重新发现启动器明确指定的本机服务；不扫描存档，也不重放玩家动作。
var runtime_path: String = ""
var expected_instance_id: String = ""
var delay_seconds: float = 1.0
var next_probe_msec: int = 0
var disconnected: bool = false
var log_path: String = ""

func configure(path: String, instance_id: String = "") -> void:
	runtime_path = path
	expected_instance_id = instance_id
	if not path.is_empty():
		log_path = path.get_base_dir().path_join("logs/client.jsonl")
		DirAccess.make_dir_recursive_absolute(log_path.get_base_dir())

func failed(reason: String) -> void:
	disconnected = true
	next_probe_msec = Time.get_ticks_msec() + int(delay_seconds * 1000)
	log_event("client.connection.lost", {"reason":reason,"retry_after_seconds":delay_seconds,"instance_id":expected_instance_id})
	delay_seconds = minf(15.0, 2.0 if delay_seconds < 2 else delay_seconds * 2)

func due() -> bool:
	return disconnected and Time.get_ticks_msec() >= next_probe_msec

func runtime() -> Dictionary:
	if runtime_path.is_empty() or not FileAccess.file_exists(runtime_path): return {}
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(runtime_path))
	if not parsed is Dictionary: return {}
	var url: String = str(parsed.get("url",""))
	var token: String = str(parsed.get("token",""))
	var instance: String = str(parsed.get("instance_id",""))
	if not url.begins_with("http://127.0.0.1:") or token.is_empty() or instance.is_empty(): return {}
	return {"url":url,"token":token,"instance_id":instance}

func discovered(value: Dictionary) -> void:
	var changed: bool = not expected_instance_id.is_empty() and expected_instance_id != str(value.instance_id)
	expected_instance_id = str(value.instance_id)
	log_event("client.runtime.discovered", {"instance_changed":changed,"instance_id":expected_instance_id})

func recovered(instance_id: String) -> void:
	expected_instance_id = instance_id
	disconnected = false
	delay_seconds = 1.0
	next_probe_msec = 0
	log_event("client.connection.recovered", {"instance_id":instance_id})

func log_event(event: String, data: Dictionary = {}) -> void:
	if log_path.is_empty(): return
	if FileAccess.file_exists(log_path):
		var current := FileAccess.open(log_path,FileAccess.READ)
		if current != null and current.get_length() >= 1024 * 1024:
			current.close()
			var reset := FileAccess.open(log_path,FileAccess.WRITE)
			if reset != null:
				reset.store_line(JSON.stringify({"time":Time.get_datetime_string_from_system(true),"event":"client.log.rotated","data":{"previous_size_limit":1024 * 1024}}))
				reset.close()
	var stream := FileAccess.open(log_path,FileAccess.READ_WRITE if FileAccess.file_exists(log_path) else FileAccess.WRITE_READ)
	if stream == null:return
	stream.seek_end()
	stream.store_line(JSON.stringify({"time":Time.get_datetime_string_from_system(true),"event":event,"data":data}))
