"""Reviewed test compositions, never a live fallback or hidden model substitute."""
import copy
from content_fixtures import authored_patch

def hybrid_patch(theme='town',opening=True):
    raw=authored_patch();r=raw['region']
    sprites=dict(hero={'asset':'dungeon_v1_adventurer'},npc={'asset':'dungeon_v1_mage'},
        enemy={'asset':'dungeon_v1_slime'},object={'asset':'dungeon_v1_crate','layers':[['ellipse',4,5,3,3,'accent']]},
        gate={'asset':'town_v1_door'},opened={'asset':'town_v1_door','layers':[['rect',5,5,6,10,'shadow']]},
        floor={'asset':'town_v1_grass' if theme=='town' else 'dungeon_v1_rubble'},
        wall={'asset':'dungeon_v1_stone'},building={'asset':'town_v1_blue_house'},tree={'asset':'town_v2_pine'},
        vial={'asset':'dungeon_v1_red_flask'},staff={'asset':'dungeon_v1_staff'},
        beacon={'size':[32,32],'parts':[{'asset':'dungeon_v1_crate','at':[8,16]}],
                'layers':[['ellipse',11,3,10,10,'accent'],['rect',15,12,2,7,'path'],['rect',14,6,4,4,'shadow']]},
        original_glow={'size':[16,16],'layers':[['ellipse',1,1,14,14,'accent'],['rect',6,2,4,12,'path'],['rect',2,6,12,4,'water']]})
    r['name']='林间邮局' if theme=='town' else '地下回声馆'
    r['visuals']=dict(style='Kenney Tiny with authored living devices',terrain='grass' if theme=='town' else 'stone',
       palette=dict(ground='#7aaa62',path='#dca268',water='#476f85',wall='#6b7183',accent='#ffd26b',shadow='#343440'),
       sprites=sprites,bindings={'object':'object','building':'building','vegetation':'tree'},scenery=[],density=0)
    r['scene']['paint'][1]['surface']='wall'
    r['landmarks']=[dict(id='post_office',type='house',zone='east',at=[20,5],sprite='building',solid=True,footprint=[3,2]),
                    dict(id='old_tree',type='tree',zone='north',at=[5,5],sprite='tree',solid=True,footprint=[2,1])]
    r['entities'][1]['sprite']='beacon'
    r['items']=[dict(id='leaf_gel',name='林间敷剂',kind='consumable',effect='heal',power=18,price=8,sprite='vial'),
                dict(id='copper_staff',name='铜环手杖',kind='weapon',effect='attack',power=2,price=18,sprite='staff')]
    if opening:r['starting_loadout']=dict(inventory=[dict(item_id='leaf_gel',count=2),dict(item_id='copper_staff',count=1)],weapon='copper_staff')
    r['program']['actions']=r['program']['actions'][:1]
    r['program']['hooks']=[h for h in r['program']['hooks'] if h['id']!='foe_logic']
    r['program']['actions'].append(dict(id='ring_beacon',label='敲响铜铃',target='lever',effects=[dict(op='sound',cue='machine')]))
    r['modules']=[dict(module='duel_v1',id='duel',args=dict(attack_label='杖击',skill_label='余光震荡',damage=15,skill_damage=22,mp_cost=3)),
                  dict(module='switch_door_v1',id='switch',args=dict(switch='lever',door='door',opened_sprite='opened',label='拨开门闩'))]
    r['audio']=dict(music=dict(explore={'asset':'music_v1_peaceful_ville' if theme=='town' else 'music_v1_synth_loop'},
                            combat={'asset':'music_v1_fairy_battles'},
                            echo={'score':{'bpm':100,'voices':[{'wave':'triangle','notes':[[60,1],[67,1],[63,2]]}]}}),
        cues=dict(step={'asset':'rpg_v1_footstep00'},hit={'asset':'rpg_v1_knife_slice'},
                  ui={'asset':'ui_v1_click_001'},machine={'layers':[{'asset':'rpg_v1_creak1','pitch':.8},
                    {'synth':{'wave':'sine','frequency':600,'duration':.2},'delay_ms':80}]}),
        bindings=dict(move='step',combat='hit',ui='ui'),objects={'lever':'machine'})
    return copy.deepcopy(raw)
