shader_type canvas_item;

uniform float flash : hint_range(0.0, 1.0) = 0.0;
uniform vec4 flash_color : source_color = vec4(1.0, 1.0, 1.0, 1.0);

void fragment() {
	vec4 ink = texture(TEXTURE, UV) * COLOR;
	COLOR = vec4(mix(ink.rgb, flash_color.rgb, flash), ink.a);
}
