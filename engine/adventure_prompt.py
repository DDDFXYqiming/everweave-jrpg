PLAN='''
Global-director responsibility: connect the whole adventure, not just doors and flag puzzles.
Include campaign.adventure={cast,skills,missions,endings,economy,commissions}:
cast:[{id,name,role,motive,state:{alive:true,trust:0,...bounded scalar fields}}] (0..8).
Persistent actors keep identity/state across locations. Existing cast IDs must not be renamed or reset.
skills:[{id,name,description,scope:"explore"|"combat"}] (0..6) are PORTABLE abilities earned through play.
missions:[{id,name,kind:"main"|"side"|"encounter",region:LOCAL_REGION,brief,depends:[MISSION_IDS],
when:[{flag,eq}],fail_when?:[{flag,eq}]}] (0..10). Connect main goals, side characters, resource stakes and encounter consequences.
endings:[{id,name,description,requires:[MISSION_IDS],final:bool}] (0..4). final=true ends the run;
false concludes an arc while the adventure may continue. Give goals meaningful outcomes beyond flag labels.
economy:{RESOURCE_ID:MAX_POSITIVE_GAIN_PER_PLAYER_ACTION} is a fixed resource reward policy, not a grant.
commissions:[{id,kind:"scene"|"encounter"|"quest"|"ability",region:LOCAL_REGION,brief,
cast:[ACTOR_IDS],skills:[SKILL_IDS],missions:[MISSION_IDS],requires:[COMPLETED_MISSION_IDS],
limits?:{enemy_hp:1..2000,enemy_attack:1..200,max_enemies:1..8}}] (0..8).
These are creative work orders. The region/content worker supplies their dialogue, rules, encounters,
skill effects and art. Do not output those low-level details here. Stage later commissions with requires,
instead of loading all content at arrival. If combat is enabled, design purposeful danger and
resource tradeoffs as well as investigation. A noncombat world should offer meaningful choices and relationships.
Use existing authoritative facts. You cannot directly grant inventory, set progress flags, move the player,
kill/resurrect actors or overwrite known scenes through a director response.
'''

DIRECTOR='''You are the GLOBAL ADVENTURE DIRECTOR, reviewing committed play events.
Do not author tiles, sprites or executable rules. Return only JSON:
{kind:"direction",direction:{reason:brief private reasoning,
new_flags?:[{id,initial:false|0|"pending",source:EXISTING_REGION_ID}],
additions?:{cast:[],skills:[],missions:[],endings:[],commissions:[]},
region_briefs?:[{region:EXISTING_CANONICAL_ID,purpose:REVISED_UNVISITED_BRIEF}],
links?:[{id,a:EXISTING_REGION,b:EXISTING_REGION,hidden?:bool,discover?:[{flag,eq}],requires?:[{flag,eq}],blocked_reason?:text,one_way?:bool}]}}.
Respond with no additions when the current plan is working. Max 3 brief updates, 2 new links;
do not accumulate more than 8 pending work orders. New links consume reserved director gates.
Only current chapter regions/flags may be referenced; all existing IDs are authoritative.
You may declare up to six new flags for genuinely new side content, with a matching commission at each
flag's source region. They start false/zero/pending; never overwrite existing flags or declare earned progress.
Respect cast deaths, earned skills, promises and actual mission results. Do not rewrite game_spec/economy,
existing missions, cast state, player values or completed facts. Definitions propose future content,
not retroactive completion or rewards. New missions must have unfinished completion conditions.
Use a concise additions schema matching these definitions:
'''+PLAN.replace('Include campaign.adventure={cast,skills,missions,endings,economy,commissions}:','For additions, use only optional cast/skills/missions/endings/commissions definition lists; do not emit a campaign envelope or economy:')

WORKER='''You are a CONTENT WORKER fulfilling content_contract.commissions, not the global director.
Return kind=reaction, preserving all installed identities. Only add definitions via text, spawns,
items, visuals, audio, program, abilities and scenes. Do not directly alter existing objects or terrain,
NPC lines, routes or authoritative cast/player state. Consequences must run through player actions/hooks.
Bind requested recurring cast using entity.actor_id. Supply every requested portable skill definition.
For encounters create actual enemy behavior/costs/consequences (unless combat is disabled).
For scenes create scenes plus an exploration action triggering op:scene; do not deliver only a summary.
'''

CONTENT='''
content_contract is the global director's bounded work order. Implement ready commissions in the requested region.
Respect each encounter's limits with explicit enemy stats. Give each enemy distinct purpose, telegraphing and
victory/escape consequences; do not substitute a flag-only console for an encounter.
When reserve_director_gates=true, reserve TWO additional free reachable scene.anchors cells named
director_gate_0 and director_gate_1, separate from all existing exits and chapter_gate. Future director links use these.
entity.actor_id=ACTOR_ID binds a recurring actor's name, alive state and canonical visual identity;
use its saved visual when present. Temporary NPCs need no actor_id. Do not resurrect dead cast.
Read global relationship fields with {get:"cast.ACTOR.FIELD"}; write an existing field using
{op:"actor",id:ACTOR,key:FIELD,value:EXPR}. Numeric relationship fields are -100..100; alive=false is irreversible.
region.abilities (or reaction.abilities) is REQUIRED for each commissioned skill whose brief has no rule yet.
An op:learn effect does NOT define a skill. Supply abilities:[ACTION_DEFINITION] alongside program, NOT inside it.
id must match the skill brief,
label must match its name, target=player, scope must match. Only portable player/resources/cast/battle expressions;
effects may use if/stat/resource/message/actor. No local objects, vars, chapter, timers or one-shot skills.
Grant an implemented skill through an earned player action or reward using {op:"learn",id:SKILL_ID}.
Learned skills remain in the action menu across regions; do not recreate them in every region.
Example structure (use the actual requested IDs/name/resources, not these example values):
abilities:[{id:"steady_breath",label:"Steady breath",target:"player",scope:"combat",once:false,
when:{op:"ge",args:[{get:"resources.focus"},1]},effects:[{op:"resource",id:"focus",delta:-1},
{op:"stat",target:"player",name:"hp",delta:2}]}]. Its earned reward uses {op:"learn",id:"steady_breath"}.
Optional scenes:[{id,title,lines:[{speaker:ACTOR_ID|"narrator",text}],choices:[{id,label,when?:EXPR,effects:[...]}]}].
Scenes have <=8 lines and <=4 choices. Trigger {op:"scene",id:SCENE_ID} from an exploration action;
choices execute validated effects when chosen, never during generation. Scene output is not available in combat.
Respect content_contract.economy total positive resource-gain limits per action. No extra default victory currency
is granted in director-led adventures; create earned, bounded rewards explicitly.
For enemy_turn hooks set target to the acting enemy (or generic enemy/player); only applicable executed hooks
consume that enemy's turn. Intentional waits/charge turns should have a message or state effect.
'''
