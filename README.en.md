# Everweave · The Unwritten Realm

> A language-model-directed 2D JRPG runtime where generated worlds become explorable, stateful game content.

[中文 README](README.md)

## What makes it different

**Campaign before map**

An online world starts with a game specification and a rolling plan for the next 2 to 4 regions, plus a private eventual outcome brief. The director can add intermediate locations and links as choices unfold. The existing full-chapter mode still supports 4 to 8 regions. Routes always come from authoritative connection records.

**A global director commissions concrete content**

The director defines persistent cast, mission dependencies, skill briefs, resource gain limits and conditional endings. Content workers implement scenes, dialogue, encounters and rules. Accumulated gameplay events can trigger a review that adds commissions, adjusts unvisited region briefs or opens limited connections. Player choices update shared cast state, and earned abilities remain usable across regions. See the [director contract](docs/ADVENTURE_DIRECTOR.md) and [validation scope](docs/ADVENTURE_VALIDATION.md).

[Fast autonomous playtesting](docs/FAST_PLAYTEST.md) uses normal game actions for continuous movement, stops at meaningful events and leaves exploration choices to the tester. Native Godot checks separately cover actual input and presentation.

The current objective sits in the upper-left map corner; click it or press Q to open known and completed objectives. Future missions are filtered in the backend. Authored enemies can guard, patrol or pursue and initiate encounters during normal local turns. Waiting exits and nearby regions receive generation priority; a no-change review no longer invalidates in-flight maps. See [pacing and encounter validation](docs/PACING_AND_ENCOUNTERS.md) for measured results and limits.

**The model creates executable content**

The model produces `scene`, `program`, `visuals`, and `audio`. An optional official Jev integration ranks assets inside the audiovisual branch and checks player-facing promises against executable effects after hard validation. It records located concerns; it does not rewrite story content or trigger whole-region retries. See [Jev integration and validation](docs/JEV_SEMANTIC_REVIEW.md). The `program` field is a bounded rule DSL that can read object state, chapter flags, resources, inventory, and recent position history. It can express switches, resource trades, combat conditions, and puzzles that depend on what happened earlier. The model submits JSON, the Python runtime validates and executes it, and Godot presents the result.

**World specifications shape the game**

A world specification can define the player title, inventory and journal labels, resource bars, system toggles for combat, inventory, equipment, and progression, along with the failure mode. The specification is saved with the world, so the interface and rules use the same world-specific vocabulary.

**Player actions leave persistent changes**

Player actions, triggers, rewards, and map changes are committed together in SQLite transactions. Nearby regions can be prepared in the background while the travel map reveals only discovered routes. Opening a door, changing a path, or reshaping an object can become part of the saved world.

**Reusable assets and original drawing work together**

The local asset index, material recipes, and bounded pixel drawing work together during generation. The model chooses theme-compatible candidates and can fill visual gaps with constrained drawing. The runtime places details from fixed seeds, verifies hashes, and records asset versions. Sound effects and short musical phrases can come from local assets or bounded recipes.

**The runtime keeps generation inside its rules**

Model output enters the game through a validated JSON content contract. It cannot submit Python, GDScript, or arbitrary file paths, and it cannot initiate network operations. Rules run inside a budgeted interpreter, and failed actions or save updates roll back.

## Current status

Everweave is still a research prototype. Campaign planning, region generation, rule validation, local execution, asset composition, the travel map, and the bilingual interface are connected in the current project. Automated tests and native Godot checks cover the main paths through these features.

Full chapter playthroughs, solvability for arbitrary generated puzzles, coverage across themes, and long-running generation quality still need continued testing in real saves. Online generation can take several minutes and consumes the selected service's allowance. A fresh data directory is recommended for a first run.

## Screenshots

The screenshots below are rendered by the Godot client. They show the current range of generated scene composition. They are visual examples and do not represent a guaranteed full-chapter playthrough for every online generation.

![Harbor repair village](docs/showcase/harbor.png)

| Underground Planetarium | Orbital Weather Station |
|---|---|
| ![Underground Planetarium](docs/showcase/ruins.png) | ![Orbital Weather Station](docs/showcase/orbital.png) |

See [Showcase](docs/SHOWCASE.md) for more scene descriptions.

## Quick start

You need Python 3.11 or newer and Godot 4 Standard. The project is currently tested with Godot 4.7.2.

Install the pinned official SDK before enabling Jev:

```powershell
py -3 -m pip install -r requirements.txt
```

On Windows, place the Godot executable in the project root or in `tools/`, then double-click `Start.cmd`. You can also start it from PowerShell.

```powershell
python launch.py --godot ./tools/Godot.exe
```

If Godot is on PATH, `python launch.py` is enough. On the first run, the launcher prepares the pinned asset manifest and verifies SHA-256 hashes. If Pillow is missing, the launcher installs the supporting tools under `userdata/library-tools` without changing the system Python environment.

## Create a world

The default is **direct ChatGPT subscription · GPT-5.6 Luna / high**. Authorize Everweave once from its connection screen, then the game reads the Responses SSE stream without Codex CLI or an OpenAI API key. Login, model or usage failures stop generation; there is no automatic paid-provider fallback. See [setup and validation](docs/CODEX_SUBSCRIPTION.md).

An online new world first generates its game specification and campaign plan, then prepares the starting region. The settings control request limits and budget; subscription mode is fixed at high, while compatible APIs expose the reasoning levels they support. The generation director prepares nearby regions, and failed tasks expose their diagnostic details with a retry action.

Subscription mode draws on the same Codex usage allowance that Codex CLI uses. DeepSeek and compatible paid APIs remain explicit manual choices, and the launcher no longer loads a DeepSeek key by default. Initial world creation and new region preparation can take time. Use the offline check to verify installation and basic controls without model calls.

Jev uses a separate TypeSafe official credential. You can store the API key as a Windows-user DPAPI ciphertext in `typesafe.local.key`, then explicitly load it for a process that should call the service:

```powershell
Read-Host -AsSecureString | ConvertFrom-SecureString | Set-Content .\typesafe.local.key
.\Start.ps1 -LoadTypeSafeKey
```

The connection screen can disable Jev. When its SDK, credential, or service is unavailable, asset selection falls back to the original catalog and semantic review is reported as incomplete rather than passed.

```powershell
python launch.py --demo --data-dir ./userdata/offline-demo
```

Each data directory stores one world. Use a separate directory when you want to keep the current journey and start another one.

```powershell
python launch.py --godot ./tools/Godot.exe --data-dir ./userdata/another-journey
```

## Controls

| Action | Key |
|---|---|
| Move | WASD or arrow keys |
| Interact with an adjacent character, object, or exit | E or Space |
| Show available custom actions | F |
| Open inventory and journal panels | I, J |
| Open the travel map | G or click the minimap |
| Wait | `.` |
| Choose a combat action | Number keys, as shown by the interface |
| Close a panel / journey menu | Esc |
| Journey drawer | Tab |
| Developer diagnostics | Ctrl+D or the menu |
| Fullscreen | Alt+Enter or display settings |
| Mute / restore all sound | M or the speaker button |

The HUD keeps location, key resources and a one-line objective. Detailed status is in the journey drawer; model and Jev telemetry is in diagnostics. Music, ambience, effects and menu sounds have independent volume controls. Sound and fullscreen preferences persist locally. See [presentation and audio verification](docs/CLIENT_PRESENTATION.md).

## Documentation

- [Local setup](docs/LOCAL_SETUP.md) covers installation, model connections, and save directories
- [Runtime architecture](docs/ARCHITECTURE.md) explains the Godot client, local service, and generation scheduling
- [Campaigns and game specifications](docs/CAMPAIGNS.md) describes campaign plans, shared clues, route graphs, and optional systems
- [Executable content](docs/EXECUTABLE_CONTENT.md) describes scenes, rules, and runtime effects
- [Hybrid content library](docs/HYBRID_CONTENT.md) covers asset references, materials, audio, and library extensions
- [Showcase](docs/SHOWCASE.md) records generated scenes and screenshots
- [Localization](docs/LOCALIZATION.md) covers the Chinese and English interface and generation language
- [Development and testing](docs/DEVELOPMENT.md) covers asset preparation and regression tests
- [Security boundaries](docs/SECURITY.md) describes local service access, credentials, and content limits
- [Documentation index](docs/README.md) collects usage notes, design documents, and experiment records

## License

Project-owned code and documentation use the [MIT License](LICENSE). Third-party assets keep their original licenses. Sources and authors are listed in [asset credits](assets/library/CREDITS.md), with additional details in [LICENSE-NOTICE.md](LICENSE-NOTICE.md).
