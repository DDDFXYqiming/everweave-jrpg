shader_type canvas_item;

uniform vec2 pixels = vec2(320.0, 200.0);
uniform vec4 tint : source_color = vec4(0.78, 0.82, 0.86, 1.0);

float hash(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float noise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	vec2 u = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
}

void fragment() {
	vec2 p = floor(UV * pixels / 2.0) * 2.0;
	float n = noise(p / 48.0 + vec2(TIME * 0.05, TIME * 0.015)) * 0.65 + noise(p / 19.0 - vec2(TIME * 0.08, 0.0)) * 0.35;
	float alpha = smoothstep(0.3, 0.95, n) * 0.26 + 0.07;
	alpha = floor(alpha * 40.0) / 40.0;
	COLOR = vec4(tint.rgb, alpha);
}
