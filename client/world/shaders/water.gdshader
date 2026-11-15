shader_type canvas_item;

varying vec2 world;

void vertex() {
	world = (MODEL_MATRIX * vec4(VERTEX, 0.0, 1.0)).xy;
}

void fragment() {
	vec4 ink = texture(TEXTURE, UV);
	vec2 cell = floor(world);
	float t = floor(TIME * 8.0) / 8.0;
	float wave = sin(cell.x * 0.45 + t * 1.7 + sin(cell.y * 0.37 + t * 0.9) * 2.0) * sin(cell.y * 0.62 - t * 1.3);
	float crest = step(0.86, wave) * step(0.95, ink.a);
	float trough = step(wave, -0.8) * step(0.95, ink.a);
	ink.rgb = mix(ink.rgb, vec3(0.92, 0.97, 1.0), crest * 0.45);
	ink.rgb *= 1.0 - trough * 0.12;
	COLOR = ink;
}
