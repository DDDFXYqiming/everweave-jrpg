extends RefCounted

const BLOCKED_TILES := [2, 3]
const STEPS := [Vector2i.LEFT, Vector2i.RIGHT, Vector2i.UP, Vector2i.DOWN]

static func rect_from_bottom_left(obj: Dictionary) -> Rect2i:
	var footprint: Array = obj.get("footprint", [1, 1])
	return Rect2i(int(obj.x), int(obj.y) - int(footprint[1]) + 1, int(footprint[0]), int(footprint[1]))

static func cells_from_bottom_left(obj: Dictionary) -> Array:
	var rect: Rect2i = rect_from_bottom_left(obj)
	var cells: Array = []
	for y in range(rect.end.y - 1, rect.position.y - 1, -1):
		for x in range(rect.position.x, rect.end.x):
			cells.append(Vector2i(x, y))
	return cells

static func interaction_cells(obj: Dictionary) -> Dictionary:
	var goals: Dictionary = {}
	for cell in cells_from_bottom_left(obj):
		goals[cell] = true
		for step in STEPS: goals[cell + step] = true
	return goals

static func blocking_cells(region: Dictionary) -> Dictionary:
	var blocked: Dictionary = {}
	for group in ["props", "entities"]:
		for obj in region.get(group, []):
			if bool(obj.get("spent", false)) or str(obj.get("kind", "")) == "exit" or not bool(obj.get("solid", group == "entities")): continue
			for cell in cells_from_bottom_left(obj): blocked[cell] = true
	return blocked

static func walk_path(region: Dictionary, start: Vector2i, goals: Dictionary, aim: Vector2i) -> Array:
	var blocked: Dictionary = blocking_cells(region)
	var width: int = int(region.width)
	var height: int = int(region.height)
	var previous: Dictionary = {start: start}
	var queue: Array = [start]
	var best: Vector2i = start
	var head: int = 0
	while head < queue.size():
		var point: Vector2i = queue[head]
		head += 1
		if goals.has(point):
			best = point
			break
		if absi(point.x - aim.x) + absi(point.y - aim.y) < absi(best.x - aim.x) + absi(best.y - aim.y): best = point
		for step in STEPS:
			var next: Vector2i = point + step
			if previous.has(next) or next.x < 0 or next.y < 0 or next.x >= width or next.y >= height: continue
			if int(region.tiles[next.y][next.x]) in BLOCKED_TILES or blocked.has(next): continue
			previous[next] = point
			queue.append(next)
	var path: Array = []
	while best != start:
		path.push_front(best)
		best = previous[best]
	return path
