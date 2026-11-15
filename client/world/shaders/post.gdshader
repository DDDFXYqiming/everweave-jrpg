shader_type canvas_item;

uniform vec3 grade = vec3(0.5);
uniform float grade_strength = 0.3;
uniform float saturation = 0.9;
uniform float vignette = 0.38;
uniform float wet = 0.0;
uniform float fade = 0.0;
uniform vec2 pixels = vec2(320.0, 200.0);

void fragment() {
	vec4 ink = texture(TEXTURE, UV);
	float luma = dot(ink.rgb, vec3(0.299, 0.587, 0.114));
	vec3 color = mix(vec3(luma), ink.rgb, saturation);
	vec3 tint = clamp(grade / max(dot(grade, vec3(0.299, 0.587, 0.114)), 0.05), vec3(0.6), vec3(1.5));
	color *= mix(vec3(1.0), tint, grade_strength);
	color = mix(color, color * vec3(0.86, 0.93, 1.06), wet * 0.5);
	vec2 cell = (floor(UV * pixels / 2.0) * 2.0 + 1.0) / pixels;
	vec2 offset = (cell - 0.5) * vec2(pixels.x / pixels.y, 1.0);
	float radius = length(offset);
	color *= 1.0 - smoothstep(0.45, 1.05, radius) * vignette;
	float reach = (1.0 - fade) * 1.0;
	color *= step(radius, reach);
	COLOR = vec4(color, 1.0);
}
