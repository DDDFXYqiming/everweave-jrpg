"""Bounded pixel drawing data. The model authors geometry, never executable code."""
import re
import copy

PALETTE=('ground','path','water','wall','accent','shadow')
ROLES=('hero','npc','enemy','building','vegetation','object')
TERRAINS=('grass','metal','stone','sand','snow','wood','void')

def freeze_sprite(recipe,palette):
    result=copy.deepcopy(recipe)
    if 'material' in result:
        result['base']=freeze_sprite(result['base'],palette)
        result['variants']=[freeze_sprite(v,palette) for v in result['variants']]
    for layers in [result.get('layers',[])]+result.get('frames',[]):
        for command in layers:command[-1]=palette.get(command[-1],command[-1])
    for part in result.get('parts',[]):
        if 'tint' in part:part['tint']=palette.get(part['tint'],part['tint'])
    return result

def resolve_sprite(name,visuals):
    from .schema import InvalidPatch
    if name in visuals['sprites']:return name
    direct=visuals.get('bindings',{}).get(name)
    if direct in visuals['sprites']:return direct
    role={'chest':'object','shrine':'object','portal':'object','crystal':'object','rock':'object','house':'building','tower':'building','camp':'building','tree':'vegetation','bush':'vegetation','flower':'vegetation','slime':'enemy','wolf':'enemy','sentinel':'enemy','wisp':'enemy','mimic':'enemy'}.get(name,name)
    if role in visuals['sprites']:return role
    target=visuals.get('bindings',{}).get(role)
    if target in visuals['sprites']:return target
    raise InvalidPatch('undefined visual sprite '+name,category='reference',value=name,
                       expected='a defined sprite or binding: '+', '.join(sorted(visuals.get('sprites',{}))[:24]))

def validate_visuals(value,minimum_layers=1):
    from .schema import InvalidPatch,obj,text,arr,ident,enum
    from .diagnostics import checked
    obj(value,'visuals',('style','terrain','palette','sprites','scenery','density','bindings'),('style','terrain','palette','sprites'))
    style=checked('visuals.style',text,value['style'],'visual style',450)
    terrain=checked('visuals.terrain',enum,value['terrain'],TERRAINS,'terrain')
    palette=obj(value['palette'],'visuals.palette',PALETTE,PALETTE)
    def color(v):
        if isinstance(v,str) and (v in PALETTE or re.fullmatch('#[0-9a-fA-F]{6}',v)):return v
        raise InvalidPatch('visual color must be #RRGGBB or a palette key')
    for key,v in palette.items():
        if not isinstance(v,str) or not re.fullmatch('#[0-9a-fA-F]{6}',v):raise InvalidPatch('palette colors must be #RRGGBB',path='visuals.palette.'+key,value=v,expected='#RRGGBB')
    sprites=value['sprites']
    if not isinstance(sprites,dict) or not 1<=len(sprites)<=48:raise InvalidPatch('visuals.sprites requires 1..48 recipes')
    location='visuals'
    def integer(n,lo,hi):
        if type(n) is not int or not lo<=n<=hi:raise InvalidPatch(f'pixel coordinate must be integer {lo}..{hi}',path=location,value=n,expected=f'integer {lo}..{hi}')
        return n
    result={}
    for key,sprite in sprites.items():
        if isinstance(sprite,dict) and 'material' in sprite:
            ident(key)
            from .materials import validate
            result[key]=validate(sprite,palette)
            continue
        if isinstance(sprite,dict) and ('asset' in sprite or 'parts' in sprite):
            result[key]=library_recipe(sprite,palette,key)
            continue
        ident(key);obj(sprite,'sprite',('size','layers','frames','frame_ms'),('size','layers'))
        size=arr(sprite['size'],'sprite.size',2,2)
        location=f'visuals.sprites.{key}.size[0]';w=integer(size[0],8,96)
        location=f'visuals.sprites.{key}.size[1]';h=integer(size[1],8,96)
        layers=[]
        for index,command in enumerate(arr(sprite['layers'],'sprite.layers',48,minimum_layers)):
            if not isinstance(command,list) or not command:raise InvalidPatch('drawing command must be an array')
            op=command[0]
            if op in ('rect','ellipse') and len(command)==6:
                location=f'visuals.sprites.{key}.layers[{index}].x';x=integer(command[1],0,w-1)
                location=f'visuals.sprites.{key}.layers[{index}].y';y=integer(command[2],0,h-1)
                location=f'visuals.sprites.{key}.layers[{index}].width';width=integer(command[3],1,w-x)
                location=f'visuals.sprites.{key}.layers[{index}].height';height=integer(command[4],1,h-y)
                layers.append([op,x,y,width,height,color(command[5])])
            elif op=='poly' and len(command)==3:
                points=[]
                for point_index,point in enumerate(arr(command[1],'polygon points',10,3)):
                    arr(point,'point',2,2)
                    location=f'visuals.sprites.{key}.layers[{index}].points[{point_index}].x';px=integer(point[0],0,w)
                    location=f'visuals.sprites.{key}.layers[{index}].points[{point_index}].y';py=integer(point[1],0,h)
                    points.append([px,py])
                layers.append([op,points,color(command[2])])
            else:raise InvalidPatch('drawing commands: [rect|ellipse,x,y,w,h,color] or [poly,[[x,y],...],color]')
        result[key]=dict(size=[w,h],layers=layers)
        if 'frames' in sprite:
            # Validate each frame using the same grammar, without nested animation.
            frames=[]
            for frame_index,commands in enumerate(arr(sprite['frames'],'frames',8,1)):
                temp=dict(style='frame',terrain='grass',palette=palette,sprites={'frame':dict(size=[w,h],layers=commands)})
                try:frames.append(validate_visuals(temp)['sprites']['frame']['layers'])
                except InvalidPatch as exc:
                    errors=[dict(entry,path=f'visuals.sprites.{key}.frames[{frame_index}]'+entry['path'].removeprefix('visuals.sprites.frame')) for entry in exc.issues]
                    raise InvalidPatch(issues=errors) from None
            result[key]['frames']=frames
            location=f'visuals.sprites.{key}.frame_ms'
            result[key]['frame_ms']=integer(sprite.get('frame_ms',180),80,1500)
    scenery=[ident(v) for v in arr(value.get('scenery',[]),'scenery',6)]
    if any(v not in result for v in scenery):raise InvalidPatch('scenery references undefined sprite')
    density=value.get('density',.045)
    if isinstance(density,bool) or not isinstance(density,(int,float)) or not 0<=density<=.12:raise InvalidPatch('scenery density must be 0..0.12')
    bindings=value.get('bindings',{})
    if not isinstance(bindings,dict) or len(bindings)>32:raise InvalidPatch('visual bindings requires at most 32 aliases')
    for alias,target in bindings.items():
        ident(alias);ident(target)
        if alias in result and alias!=target:raise InvalidPatch('sprite alias conflicts with an existing definition',value=alias)
    if any(v not in result for v in bindings.values()):raise InvalidPatch('visual binding references undefined sprite')
    out=dict(style=style,terrain=terrain,palette=dict(palette),sprites=result,scenery=scenery,density=density)
    if bindings:out['bindings']=dict(bindings)
    return out


def library_recipe(sprite,palette,key):
    from .schema import InvalidPatch,obj,ident,arr
    from .content import integer,boolean
    from .library import resolve
    ident(key)
    obj(sprite,'library sprite',('asset','asset_hash','parts','size','layers','frames','frame_ms','tint','flip_x'))
    out={}
    if 'asset' in sprite:
        entry=resolve(sprite['asset'],'image',sprite.get('asset_hash'))
        out=dict(asset=sprite['asset'],asset_hash=entry['sha256'],size=entry['size'])
        if 'size' in sprite and sprite['size']!=entry['size']:raise InvalidPatch('asset size is fixed; use a scaled part for a resized composition',value=sprite['asset'])
        if 'parts' in sprite:raise InvalidPatch('use either asset or parts for the base')
    else:
        size=arr(sprite.get('size'),'composite size',2,2)
        out['size']=[integer(n,8,96,'composite size') for n in size]
        out['parts']=[]
        for part in arr(sprite['parts'],'sprite parts',16,1):
            obj(part,'sprite part',('asset','asset_hash','at','scale','tint','flip_x'),('asset','at'))
            entry=resolve(part['asset'],'image',part.get('asset_hash'))
            at=arr(part['at'],'part at',2,2);scale=integer(part.get('scale',1),1,4,'part scale')
            x,y=[integer(n,0,95,'part position') for n in at]
            if x+entry['size'][0]*scale>out['size'][0] or y+entry['size'][1]*scale>out['size'][1]:raise InvalidPatch('library part exceeds composition canvas',value=part['asset'])
            normalized=dict(asset=part['asset'],asset_hash=entry['sha256'],at=[x,y],scale=scale)
            for option in ('tint','flip_x'):
                if option in part:normalized[option]=part[option]
            out['parts'].append(normalized)
    for option in ('tint','flip_x'):
        if option in sprite:out[option]=sprite[option]
    for transform in [out]+out.get('parts',[]):
        if 'flip_x' in transform:transform['flip_x']=boolean(transform['flip_x'])
        if 'tint' in transform and (not isinstance(transform['tint'],str) or not re.fullmatch('#[0-9a-fA-F]{6}',transform['tint'])):raise InvalidPatch('tint requires #RRGGBB')
    if sprite.get('layers'):
        value=dict(style='overlay',terrain='grass',palette=palette,sprites={key:dict(size=out['size'],layers=sprite['layers'])})
        out['layers']=validate_visuals(value,1)['sprites'][key]['layers']
    if 'frames' in sprite:
        out['frames']=[]
        for frame in arr(sprite['frames'],'frames',8,1):
            value=dict(style='frame',terrain='grass',palette=palette,sprites={key:dict(size=out['size'],layers=frame)})
            out['frames'].append(validate_visuals(value,1)['sprites'][key]['layers'])
        out['frame_ms']=integer(sprite.get('frame_ms',180),80,1500,'frame_ms')
    return out

VISUAL_PROMPT='''
For regions, visuals is REQUIRED; for reactions, provide it only when new shapes are needed: author ORIGINAL pixel drawing recipes matching this world's specific setting.
Do not reuse the default medieval forest look for science fiction, underwater, space, cities or other themes.
visuals = {style: short art-direction name, terrain: grass/metal/stone/sand/snow/wood/void,
 palette: {ground:"#RRGGBB",path:"#RRGGBB",water:"#RRGGBB",wall:"#RRGGBB",accent:"#RRGGBB",shadow:"#RRGGBB"},
 sprites: {unique_object_id:recipe,...themed named recipes}; opening region must include hero, later regions reuse hero_visual,
 bindings: {building:"building_recipe_id",vegetation:"scenery_recipe_id",object:"object_recipe_id"},
 scenery:[sprite IDs to scatter, can be empty], density:0..0.12}.
Each recipe = {size:[width,height],layers:[drawing commands in back-to-front order]}.
Size is 8..96 wide/high. 1..48 layers per sprite. Use 6..12 recipes normally, at most48. Optional frames:[layer-arrays] (1..8), frame_ms:80..1500. Frames share size/palette; no nested recipes. Use 16x16 tile recipes through scene.paint.surface for original floors.
Commands: ["rect",x,y,width,height,color], ["ellipse",x,y,width,height,color], or ["poly",[[x,y],...],color].
All coordinates integers within the canvas. Rectangles must fit x+width<=canvas width,y+height<=canvas height.
Colors are #RRGGBB or palette key names. 3..10 vertices per polygon. No URLs, files, text drawing or code.
Design recognizable silhouettes, 2-3 shade levels, outlines, highlights and small pixel details (roughly 8..16 layers per recipe).
Sprites are rendered at 2x; hero/npc around 16x28, buildings around 48x56. Leave transparent space outside the silhouette.
The vegetation binding can be coral, antennas, fungi, crystals or machinery as appropriate; it does not have to be a tree.
Entities and landmarks can optionally set sprite:"recipe_id" to use a distinct recipe; otherwise semantic role defaults apply.
Build visually distinct characters and architecture, not just a palette swap. Newly invented visual motifs should fit prior visual identity.
'''
