extends RefCounted
## Read-only projections of the existing snapshot. Never repairs engine content,
## evaluates rules, changes IDs, or sends synthesized actions to the backend.
const KINDS := {"consumable":"补给", "weapon":"武器", "charm":"饰物", "key":"要物", "tool":"工具"}

static func records(value: Variant) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	if value is Array:
		for entry in value:
			if entry is Dictionary: result.append(entry)
	return result

static func inventory(snapshot: Dictionary, category: String = "all") -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for raw in records(snapshot.get("inventory", [])):
		if str(raw.get("id", "")).is_empty() or int(raw.get("quantity", 0)) <= 0: continue
		var kind: String = str(raw.get("kind", "tool"))
		if category != "all" and kind != category: continue
		var item: Dictionary = raw.duplicate(true)
		item["kind"] = kind
		item["type_label"] = KINDS.get(kind, "物品")
		var use: Dictionary = raw.get("use", {}) if raw.get("use") is Dictionary else {}
		item["can_use"] = not bool(raw.get("equipped", false)) and (not use.is_empty() or kind in ["consumable", "weapon", "charm"])
		item["action_label"] = str(use.get("label", "装备" if kind in ["weapon", "charm"] else "使用"))
		result.append(item)
	return result

static func objectives(snapshot: Dictionary, status: String = "active") -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for q in records(snapshot.get("quests", [])):
		if status == "all" or str(q.get("status", "active")) == status: result.append(q)
	return result

static func prose(value: Variant) -> String:
	if value is String: return value
	if value is Dictionary:
		for key in ["text", "description", "note", "message"]:
			if value.get(key) is String: return value[key]
	return ""

static func history(snapshot: Dictionary) -> Array[String]:
	var result: Array[String] = []
	var entries: Variant = snapshot.get("journal", [])
	if entries is Array:
		for entry in entries:
			var line: String = prose(entry)
			if not line.is_empty(): result.append(line)
	result.reverse()
	return result

static func summary(snapshot: Dictionary) -> String:
	var d: Dictionary = snapshot.get("director", {})
	var failed: int = records(d.get("failed_tasks", [])).size()
	if bool(d.get("paused", false)): return "已暂停准备新内容"
	if failed > 0: return "%d 处内容需要重试" % failed
	if bool(snapshot.get("started",false)) and not snapshot.get("region") is Dictionary: return "正在准备第一处落脚地"
	if int(d.get("active_requests", 0)) > 0: return "正在准备沿途的新内容"
	if d.get("mode") == "not_configured": return "继续旅程后准备新内容"
	return "沿途内容已就绪"
