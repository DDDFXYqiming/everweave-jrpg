"""Bounded pixel drawing data. The model authors geometry, never executable code."""
import re
import copy

PALETTE=('ground','path','water','wall','accent','shadow')
ROLES=('hero','npc','enemy','building','vegetation','object')
TERRAINS=('grass','metal','stone','sand','snow','wood','void')

def freeze_sprite(recipe,palette):
    result=copy.deepcopy(recipe)
    for command in result['layers']:command[-1]=palette.get(command[-1],command[-1])
    return result

def resolve_sprite(name,visuals):
    from .schema import InvalidPatch
    if name in visuals['sprites']:return name
    role={'chest':'object','shrine':'object','portal':'object','crystal':'object','rock':'object','house':'building','tower':'building','camp':'building','tree':'vegetation','bush':'vegetation','flower':'vegetation','slime':'enemy','wolf':'enemy','sentinel':'enemy','wisp':'enemy','mimic':'enemy'}.get(name,name)
    if role in visuals['sprites']:return role
    target=visuals.get('bindings',{}).get(role)
    if target in visuals['sprites']:return target
    raise InvalidPatch('undefined visual sprite '+name)

def validate_visuals(value):
    from .schema import InvalidPatch,obj,text,arr,ident,enum
    obj(value,'visuals',('style','terrain','palette','sprites','scenery','density','bindings'),('style','terrain','palette','sprites'))
    palette=obj(value['palette'],'visuals.palette',PALETTE,PALETTE)
    def color(v):
        if isinstance(v,str) and (v in PALETTE or re.fullmatch('#[0-9a-fA-F]{6}',v)):return v
        raise InvalidPatch('visual color must be #RRGGBB or a palette key')
    for key,v in palette.items():
        if not isinstance(v,str) or not re.fullmatch('#[0-9a-fA-F]{6}',v):raise InvalidPatch('palette colors must be #RRGGBB')
    sprites=value['sprites']
    if not isinstance(sprites,dict) or not 3<=len(sprites)<=16:raise InvalidPatch('visuals.sprites requires 3..16 recipes')
    if {'hero','npc','enemy'}-set(sprites):raise InvalidPatch('visuals.sprites requires hero, npc, enemy recipes')
    def integer(n,lo,hi):
        if type(n) is not int or not lo<=n<=hi:raise InvalidPatch(f'pixel coordinate must be integer {lo}..{hi}')
        return n
    result={}
    for key,sprite in sprites.items():
        ident(key);obj(sprite,'sprite',('size','layers'),('size','layers'))
        size=arr(sprite['size'],'sprite.size',2,2)
        w=integer(size[0],8,64);h=integer(size[1],8,80)
        layers=[]
        for command in arr(sprite['layers'],'sprite.layers',48,3):
            if not isinstance(command,list) or not command:raise InvalidPatch('drawing command must be an array')
            op=command[0]
            if op in ('rect','ellipse') and len(command)==6:
                x=integer(command[1],0,w-1);y=integer(command[2],0,h-1)
                width=integer(command[3],1,w-x);height=integer(command[4],1,h-y)
                layers.append([op,x,y,width,height,color(command[5])])
            elif op=='poly' and len(command)==3:
                points=[]
                for point in arr(command[1],'polygon points',10,3):
                    arr(point,'point',2,2);points.append([integer(point[0],0,w),integer(point[1],0,h)])
                layers.append([op,points,color(command[2])])
            else:raise InvalidPatch('drawing commands: [rect|ellipse,x,y,w,h,color] or [poly,[[x,y],...],color]')
        result[key]=dict(size=[w,h],layers=layers)
    scenery=[ident(v) for v in arr(value.get('scenery',[]),'scenery',6)]
    if any(v not in result for v in scenery):raise InvalidPatch('scenery references undefined sprite')
    density=value.get('density',.045)
    if isinstance(density,bool) or not isinstance(density,(int,float)) or not 0<=density<=.12:raise InvalidPatch('scenery density must be 0..0.12')
    bindings=obj(value.get('bindings',{}),'visual bindings',ROLES)
    if any(v not in result for v in bindings.values()):raise InvalidPatch('visual binding references undefined sprite')
    out=dict(style=text(value['style'],'visual style',80),terrain=enum(value['terrain'],TERRAINS,'terrain'),palette=dict(palette),sprites=result,scenery=scenery,density=density)
    if bindings:out['bindings']=dict(bindings)
    return out

VISUAL_PROMPT='''
region.visuals is REQUIRED: author ORIGINAL pixel drawing recipes matching this world's specific setting.
Do not reuse the default medieval forest look for science fiction, underwater, space, cities or other themes.
visuals = {style: short art-direction name, terrain: grass/metal/stone/sand/snow/wood/void,
 palette: {ground:"#RRGGBB",path:"#RRGGBB",water:"#RRGGBB",wall:"#RRGGBB",accent:"#RRGGBB",shadow:"#RRGGBB"},
 sprites: {hero:recipe,npc:recipe,enemy:recipe,...themed named recipes},
 bindings: {building:"building_recipe_id",vegetation:"scenery_recipe_id",object:"object_recipe_id"},
 scenery:[sprite IDs to scatter, can be empty], density:0..0.12}.
Each recipe = {size:[width,height],layers:[drawing commands in back-to-front order]}.
Size is 8..64 wide, 8..80 high. 3..48 layers per sprite. Use 6..10 recipes normally, at most 16.
Commands: ["rect",x,y,width,height,color], ["ellipse",x,y,width,height,color], or ["poly",[[x,y],...],color].
All coordinates integers within the canvas. Rectangles must fit x+width<=canvas width,y+height<=canvas height.
Colors are #RRGGBB or palette key names. 3..10 vertices per polygon. No URLs, files, text drawing or code.
Design recognizable silhouettes, 2-3 shade levels, outlines, highlights and small pixel details (roughly 8..16 layers per recipe).
Sprites are rendered at 2x; hero/npc around 16x28, buildings around 48x56. Leave transparent space outside the silhouette.
The vegetation binding can be coral, antennas, fungi, crystals or machinery as appropriate; it does not have to be a tree.
Entities and landmarks can optionally set sprite:"recipe_id" to use a distinct recipe; otherwise semantic role defaults apply.
Build visually distinct characters and architecture, not just a palette swap. Newly invented visual motifs should fit prior visual identity.
'''
