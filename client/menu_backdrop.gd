extends Control
## Quiet cartographic decoration, independent of generated game art.
func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	resized.connect(queue_redraw)
func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO,size),Color("101715"))
	var ink := Color(0.63,0.66,0.51,0.10)
	for n in range(13):
		var points := PackedVector2Array()
		for i in range(65):
			var a: float = float(i)/64.0*TAU
			var radius: float = 64.0+n*28.0+sin(a*3.0+n*.12)*23.0+cos(a*5.0)*12.0
			points.append(size*Vector2(.23,.62)+Vector2(cos(a)*radius,sin(a)*radius*.7))
		draw_polyline(points,ink,1.0,true)
	for x in range(40,int(size.x),80):
		for y in range(40,int(size.y),80): draw_circle(Vector2(x,y),1,Color(.7,.7,.6,.08))
