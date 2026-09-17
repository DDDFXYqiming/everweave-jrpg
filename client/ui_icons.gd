extends RefCounted
## Original 16-pixel silhouettes; shared HUD and fieldbook vocabulary.
static var cache: Dictionary = {}
const SHAPES := {
	"bag": ["    ####    ","   #    #   ","   #    #   ","  ########  "," ##      ## "," #  ####  # "," #  #  #  # "," #  ####  # "," #        # "," ########## "],
	"book": [" ##### #####", "#     #     #", "# ### # ### #", "#     #     #", "# ### # ### #", "#     #     #", "# ### # ### #", "#     #     #", " ##### ##### "],
	"settings": ["    ####    "," ## #### ## "," ########## ","###  ##  ###","###      ###","###      ###","###  ##  ###"," ########## "," ## #### ## ","    ####    "],
	"compass": ["  ########  "," ##      ## "," #     ## # ","##    ##  ##","##   ##   ##","##  ##    ##"," # ##     # "," ##      ## ","  ########  "],
	"quest": [" ########## "," #        # "," #  ####  # "," #    ##  # "," #   ##   # "," #        # "," #   ##   # "," #        # "," ########## "],
	"sound_on": ["     ##     ","    ###  #  "," ######   # "," ###### #  #"," ###### #  #"," ######   # ","    ###  #  ","     ##     "],
	"sound_off": ["     ##     ","    ###     "," ###### #  #"," ######  ## "," ######  ## "," ###### #  #","    ###     ","     ##     "],
	"warning": ["     ##     ","    ####    ","   ##  ##   ","  ## ## ##  "," ##  ##  ## ","##        ##","##   ##   ##","############"],
	"generation": ["     ##     ","     ##     "," #  ####  # ","  ########  ","############","  ########  "," #  ####  # ","     ##     ","     ##     "],
	"screen": ["####    ####","#          #","#          #","            ","            ","#          #","#          #","####    ####"],
	"close": ["##        ##"," ##      ## ","  ##    ##  ","   ##  ##   ","    ####    ","   ##  ##   ","  ##    ##  "," ##      ## ","##        ##"],
	"consumable": ["    ####    ","    #  #    ","    #  #    ","   ##  ##   ","  ##    ##  "," ## #### ## "," # ###### # "," # ###### # "," ########## "],
	"weapon": ["         ###","        ####","       #### ","      ####  "," ##  ####   ","  ######    ","   ####     ","  ######    "," ####  ##   ","###         "],
	"charm": ["     ##     ","    ####    ","   ##  ##   ","  ##    ##  "," ########## ","  ## ## ##  ","   #####    ","    ###     ","     #      "],
	"key": ["  ####      "," ##  ##     "," #    #     "," ##  ##     ","  ######    ","      ##    ","      ##### ","      ##    ","      ##### "],
	"tool": [" ##    ##   "," ##    ##   "," ########   ","  ######    ","    ##      ","    ##      ","    ##      ","   ####     ","   ####     "]
}
static func get_icon(name: String) -> Texture2D:
	if name == "sound": name = "sound_on"
	if cache.has(name): return cache[name]
	var pattern: Array = SHAPES.get(name, SHAPES.bag)
	var image := Image.create(16, 16, false, Image.FORMAT_RGBA8)
	image.fill(Color.TRANSPARENT)
	var y_offset: int = (16 - pattern.size()) / 2
	for y in range(pattern.size()):
		var line: String = pattern[y]
		for x in range(mini(line.length(),14)):
			if line[x] == "#": image.set_pixel(x+1,y+y_offset,Color("e2d2a8"))
	image.resize(32,32,Image.INTERPOLATE_NEAREST)
	cache[name] = ImageTexture.create_from_image(image)
	return cache[name]
