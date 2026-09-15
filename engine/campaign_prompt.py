PROMPT='''Design one coherent CHAPTER of a continuing playable adventure, not a list of unrelated rooms.
Return JSON {"kind":"campaign","campaign":{...}}. Write player-facing text in Chinese unless instructed otherwise.
campaign fields: title, premise, goal (clear player objective, stakes and direction), flags:{bare_id:bool/int/string},
flag_sources:{FLAG:REGION_ID}, regions:[{id,name,description,purpose}], links:[{id,a,b,hidden?:bool,
discover?:[{flag,eq}],requires?:[{flag,eq}],blocked_reason?:text,one_way?:bool}], milestones:[{id,name,description,when:[{flag,eq}]}],
complete_when:[{flag,eq}], continuation:{from:REGION_ID,hook:next chapter promise}.
For new online adventures use planning:"rolling": author only the next 2..4 regions, connected by 1..6 links.
Include ending_brief: a PRIVATE eventual outcome direction, not a complete intermediate route. Keep the middle open
for the global director to expand as the player makes choices. Plan a playable local arc and its continuation,
with room for danger, negotiation and character scenes. Do not prewrite a whole campaign as a puzzle checklist.
The legacy planning:"chapter" supports 4..8 regions, 4..14 links with a loop and junction of degree>=3 (max6).
Links are bidirectional unless one_way=true from a to b. Future expansion should add meaningful branches and loops.
Every region must be structurally reachable from the first, respecting direction. Do not trap required progress behind a one-way return.
Region IDs <=20, link IDs <=40 lowercase snake_case. The FIRST region is the arrival; allow an initially open visible route from it.
Include meaningful branches, optional encounters and a discoverable hidden shortcut when appropriate.
Use clear cross-region dependencies: investigate A -> gain a shared clue/ability -> open a route or solve a goal in B.
Conditions are AND lists; eq must match the flag's initial type. Every flag needs one producer region in flag_sources.
Assign each region a distinct role in THIS story, with NPC motives, danger or discovery and consequences.
State which concrete player action writes each produced flag in that region's purpose. Do not put the only key behind its own locked route.
Use goal and premise for the player's known problem and stakes; keep solutions and future revelations in private purposes.
At least one unfinished milestone and completion condition. A completed chapter must offer a next chapter via continuation.from;
the region generator will reserve an anchor for it. Preserve the previous chapter's consequences, setting and identity.
Do NOT draw assets, map tile arrays or entire executable programs at this planning stage. Be concise.
For the FIRST chapter (world_context.game_spec is null) also provide game_spec:
{identity:player role,inventory_label:setting term,journal_label:setting term,visual_theme:precise period/genre/material direction,
systems:{combat:bool,inventory:bool,equipment:bool,progression:bool},
resources:[{id,label,initial,max,display:"bar"|"number"}]}.
Optional failure_mode is checkpoint (return to entry, recover hp, no automatic currency loss),
end (the run ends at hp=0), or none for noncombat worlds. hp means remaining health: higher is healthier.
0..8 resources. Built-ins hp (combat requires it), mp, gold are OPTIONAL except hp when combat is enabled.
Additional IDs like ammo, infection, battery, heat are real bounded resources available to authored rules.
Choose systems for the premise: cozy delivery can disable combat, health, magic and progression entirely;
modern survival horror can use hp/ammo/infection, no mp/gold/levels. Do not merely rename magic to ammo.
Equipment requires inventory. Subsequent chapters MUST omit game_spec and preserve the existing specification.
Modern hospitals, infection horror and laboratories must keep their modern identity. Do not turn them into medieval dungeons.
Reuse suitable library assets later; original drawing remains available when the library lacks a fitting asset.
'''
from .adventure_prompt import PLAN
PROMPT+='\n'+PLAN

REGIONAL='''
WHEN chapter_plan is supplied, it overrides the legacy destination rules:
Do NOT invent region.destinations, back, or forward_N routes. Omit destinations entirely.
For EACH planned_routes entry provide scene.anchors[entry.anchor] at a distinct free reachable tile,
including hidden/locked/inbound-only routes. The engine creates exits with the chapter graph's allowed direction.
If reserve_chapter_gate=true also reserve a free reachable scene.anchors.chapter_gate for continuation.
Follow region_purpose: NPC motives, threats, clues and consequences must advance this chapter's goal.
Every required_flag_writes key MUST have a purposeful player action/hook writing it with
{op:"chapter",key:FLAG,value:EXPRESSION}. Read shared flags with {get:"chapter.FLAG"} across this chapter.
Implement each producer in its assigned region. Explain clues without revealing hidden roads early.
Example: power station switch writes power=true; archive scanner reads chapter.power. Do not substitute unrelated local vars.
Respect game_spec.systems and resources. Omitted hp/mp/gold are disabled, not invisible spare resources.
Custom resources use {get:"resources.ID"} and {op:"resource",id:ID,delta:EXPRESSION}, bounded by game_spec.
Stat effects on player hp/mp/gold require that resource. No combat -> no enemies/combat actions/death penalties.
No equipment -> no weapon/charm items. No inventory -> items=[], starting_loadout={inventory:[]} at r0.
Use generic object with custom resource effects instead of a legacy healer/shrine or default merchant when its systems are disabled.
Keep the requested visual setting; draw original pixels when no library asset fits the role.
'''
