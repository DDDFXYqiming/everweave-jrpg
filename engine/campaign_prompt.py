PROMPT='''Design one coherent CHAPTER of a continuing playable adventure, not a list of unrelated rooms.
Return JSON {"kind":"campaign","campaign":{...}}. Write player-facing text in Chinese unless instructed otherwise.
campaign fields: title, premise, goal (clear player objective, stakes and direction), flags:{bare_id:bool/int/string},
flag_sources:{FLAG:REGION_ID}, item_sources?:{ITEM_ID:{region:REGION_ID,count?:1..9}}, regions:[{id,name,description,purpose}],
links:[{id,a,b,hidden?:bool,discover?:[COND],requires?:[COND],blocked_reason?:text,one_way?:bool}], milestones:[{id,name,description,when:[COND]}],
complete_when:[COND], continuation:{from:REGION_ID,hook:next chapter promise}.
COND is one of {flag,eq} | {item:ITEM_ID,count?} (player holds >=count of a chapter key item from item_sources)
| {ability:SKILL_ID} (an adventure skill was learned) | {mission:MISSION_ID,status:"active"|"complete"|"failed"}.
item_sources declares key items whose producer region must make them obtainable once; requires inventory.
The engine exhaustively searches the chapter graph: arriving at a region grants its flag_sources/item_sources writes and
its commissioned skills. The plan is rejected if no final ending (or, without one, the chapter completion) is reachable,
if any planned region is never reachable, or if some reachable state can no longer finish (softlock: key only behind
its own door, one-way trap, failable mission on the only path).
REAL LOCK REQUIRED: every way to the completion/final ending must pass at least one locked route: a link whose requires is
false at chapter start, or a hidden link opened by discover. Its key (flag, item_sources item or newly taught skill) is earned
elsewhere first. The engine deletes every initially open route and rejects the plan if the goal is still reachable.
world_context.player_abilities lists skills the player ALREADY has; requiring them is not a lock, but later chapters may use
them to open shortcuts. Each region later gets an exact in-region search: it must really produce its flag_sources values and
item_sources items with reachable actions, and consuming them must never softlock the region.
For new online adventures use planning:"rolling": author only the next 3..4 regions, connected by 2..6 links, so a lock fits.
Include ending_brief: a PRIVATE eventual outcome direction, not a complete intermediate route. Keep the middle open
for the global director to expand as the player makes choices. Plan a playable local arc and its continuation,
with room for danger, negotiation and character scenes. Do not prewrite a whole campaign as a puzzle checklist.
The legacy planning:"chapter" supports 4..8 regions, 4..14 links with a loop and junction of degree>=3 (max6).
Links are bidirectional unless one_way=true from a to b. Future expansion should add meaningful branches and loops.
Every region must be structurally reachable from the first, respecting direction. Do not trap required progress behind a one-way return.
Region IDs <=20, link IDs <=40 lowercase snake_case. The FIRST region is the arrival; allow an initially open visible route from it.
Include meaningful branches, optional encounters and a discoverable hidden shortcut when appropriate.
Use clear cross-region dependencies: investigate A -> gain a shared clue/ability -> open a route or solve a goal in B.
Conditions are AND lists; flag eq must match the flag's initial type. Every flag needs one producer region in flag_sources.
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
Every required_item_grants entry MUST be an items definition with exactly that id, obtainable here count times
(chest or {op:"item",id,count}); chapter links and missions gate on it. Gate local rules on a learned skill with {has_ability:SKILL_ID}.
A key produced by ANOTHER region is read with its canonical id {item:"PRODUCER_REGION:ITEM_ID"} (producer from chapter_plan.item_sources);
never redefine it in region.items, because a local copy is a different item the player can never hold.
The engine replays this region with the real interpreter over every reachable state (walking, talking, choices, actions,
item uses, fights). It rejects the region unless each required flag value and item is actually reachable, a promised key is
not only behind a lock that needs that same key, no reachable state loses the chance to obtain it (a consumed or burned key,
an irreversible switch, a wall that seals the producer), and some open exit stays reachable. Foreign flags/items/skills the
chapter can provide before arriving are assumed available; keep local puzzle states small (a few switches, not counters).
Implement each producer in its assigned region. Explain clues without revealing hidden roads early.
Example: power station switch writes power=true; archive scanner reads chapter.power. Do not substitute unrelated local vars.
Respect game_spec.systems and resources. Omitted hp/mp/gold are disabled, not invisible spare resources.
Custom resources use {get:"resources.ID"} and {op:"resource",id:ID,delta:EXPRESSION}, bounded by game_spec.
Stat effects on player hp/mp/gold require that resource. No combat -> no enemies/combat actions/death penalties.
No equipment -> no weapon/charm items. No inventory -> items=[], starting_loadout={inventory:[]} at r0.
Use generic object with custom resource effects instead of a legacy healer/shrine or default merchant when its systems are disabled.
Keep the requested visual setting; draw original pixels when no library asset fits the role.
'''
