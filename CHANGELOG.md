# Changelog

## 2026-11-12: Android RC2 — APK único de teste

- O fork Android agora tem APK único ARM64 para instalação direta, reunindo
  base, bibliotecas ARM64, inglês e recursos mdpi, sem o split francês.
- Revival executa no próprio processo Android em `127.0.0.1:18080`;
  título, Home e Vortex foram verificados no Waydroid. A segunda abertura
  não repetiu o download de ~224 MB.
- O APK utiliza certificado de teste, não contém os 19 pacotes de dados e
  ainda precisa ser validado em celular ARM64 físico, sem rede, incluindo
  uma batalha e persistência do save. Não publicar binários proprietários.
- A documentação iOS original abaixo permanece como histórico do upstream.

Each entry is one update to this repo. To update: in your repo folder run `git pull`, then from `ios-server` run `docker compose build`, `docker compose run --rm server fetch-data` and `docker compose up -d`. Your save isn't touched. Open the game twice afterwards so it picks up the new data. If you downloaded the ZIP instead of using git, see **Updating** in the README.

## 2026-11-13 update: read this first

**This update downloads new data. Follow these steps exactly.** In your `ios-server` folder, run each line on its own:

```
git pull
docker compose build
docker compose run --rm server fetch-data
docker compose up -d
```

`fetch-data` downloads about 0.3 GB of summon art this time and should end with `installed summon-art`. Then close the game fully and open it twice.

**Convert to Prism / Fragments** work from the second time you open the game after updating. In the first session, go to Menu → return to the title screen → start again, and they'll show your units.

**New to this?**
- **Docker Desktop is required:** [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/). On Windows, if it won't start, hardware virtualization may be off in your BIOS. Keep Docker Desktop open while the server runs.
- **Git is optional.** Without it, update by ZIP: on GitHub, use Code → Download ZIP, replace your `exvius/repo` folder with the new files, and copy your old `ios-server/.env` into the new `ios-server` folder. Your save and game data are outside `repo`, so they're kept. Then run the last three lines above.
- **Want git?** Windows: [git-scm.com/download/win](https://git-scm.com/download/win), default options, then open a new PowerShell. Mac: type `git --version` in Terminal and click Install when asked.

The entries below, from here down to "5★ Select list, summon pools…", are all part of this update.

## 2026-11-13: Summon buttons and the moogle's line on the large detail screen

- On the larger summon detail screen (step-ups, free and ticket summons, and paid summons with full-size art such as Dark Fina Revealed) the Summon and 11 Summons buttons had an empty Lapis bar with the price underneath. That screen now uses the game's large buttons, with the price inside the bar. The paid summons' own screen keeps its gold buttons.
- The moogle on that screen said "Summon 1 reward(s). The button shows the cost..." for almost every summon. It now says what the summon does, for example "Summon 11 for at least one 4★ or higher unit, kupo!". Summons that have the game's own text keep it.
- New setting `EXVIUS_SUMMON_SCREEN_BUTTONS` (see the README).

## 2026-11-13: Convert lists from a fresh start

- The Nov 11 and Nov 12 entries that said the Convert lists were fixed were wrong. Convert to Prism and Convert to Fragments stayed empty every time the game was opened fresh; they only filled after Menu → return to the title screen → start again.
- The cause: the game only takes the Convert table into its list of tables if another of its tables is already loaded when the title screen opens, and the server sent that table's version too late. The server now names it just before the title screen.
- It does this only once it knows your phone has that table: from the second time you open the game after this update (and after a new install or a new game). In the first session the lists are still empty; the manual way above still works.
- New setting `EXVIUS_CONVERT_EARLY_TABLE` (see the README). `docker compose logs server | grep CONVERT-TABLE` shows what the server did at each launch.

## 2026-11-13: Summon list: the game's own banners are whole again

- After the last update the summon list showed only a strip from the bottom of 39 banners from 2016 and 2017 (Dark Fina Revealed, Final Fantasy Type-0 and others): the names and the title, with the units cut off. The game's own list banners are shown whole again.
- Those summons still open the larger detail screen with the whole art. Strips are only cut from news images and Japanese banners, where no list banner survives.
- No new download: `fetch-data` has nothing to fetch for this.

## 2026-11-13: Summon art comes with the game data

- Run `docker compose run --rm server fetch-data` once after this update. It downloads one new pack (about 310 MB) with the summon banner art.
- The server no longer downloads banner art from the internet while it runs, and no longer draws or pads banners on the fly. Every summon image is a finished file, so the summon screen opens the same way with or without an internet connection.
- With the default settings the game server downloads nothing from the internet. The only download is `fetch-data`, from this project's data releases.
- 151 more summons have real art in place of a plain titled banner: 101 with a news image from Global's archived announcements, and 50 with the Japanese banner of the same summon where no English one survives (2023 featured summons and raid summons).
- Summons whose art is lost show a plain titled banner sized for their screen, instead of a small one between blurred sides.
- New settings `EXVIUS_SUMMON_ART_PACK` and `EXVIUS_EVENT_ART_FETCH`; `EXVIUS_DEAL_ART_FETCH` is now off unless you turn it on (see the README).

## 2026-11-13: Brave Shift forms from summons

- Summons could give a unit's Brave Shift form as a unit of its own: a copy that can't be awakened. Eight summons did this, among them Royal Puppeteer Aphmau, Curse of Immunity Melissa, Lunar Festival Cleome and World's Hero Gilgamesh. No summon gives a form any more; these summons give the unit itself.
- If you already have such a copy, it turns into the real unit the next time you open the game. It keeps its place in your box and parties, its equipment, materia and Vision Card, and its level up to the unit's maximum. A copy of an awakened 5★ unit's Neo Vision form becomes the 5★ unit (or the 3★ unit for Gau), which you can then awaken normally.
- The featured Neo Vision units of those eight summons are at 1% each, as on Global. Before, a unit and its form shared the chance or doubled it.
- Drop Rates pages no longer list the same unit twice.
- New setting `EXVIUS_SUMMON_NO_SHIFT_FORMS` (see the README).

## 2026-11-13: Summon art on the right screen

- Summon pages that showed small art between blurred sides (step-ups, free and ticket summons, 10+1 deals) now show the art across the frame.
- 59 paid summons whose art is the tall kind open the screen that fits it. Their prices are the same.
- The summon list no longer has giant square tiles: a news or Japanese picture that isn't a strip gets a strip cut from it.
- New setting `EXVIUS_SUMMON_SCREENS` (see the README).

## 2026-11-13: Battle item set

- The battle item set went back up to its old count after a Vortex battle such as the Chamber of the Fallen, and stayed there after a restart, even when you had no spare items. The game refills the set from your bag by itself after those battles, and the server was counting the items in the set as still in the bag. It no longer does: the set only refills from items you really have left.
- The Items tab now shows the items that are not in the set, as the game counts them. If you own 25 Potions and carry 10, it shows 15.
- A set that was filled from items you didn't have is lowered to what you own the next time you open the game.
- New setting `EXVIUS_ITEM_SET_BAG` (see the README).

## 2026-11-13: Kilika Woods, random battles in three events

- Kilika Woods - Exploration: after the Opening no further quest was offered. Its explorations are listed now, also for a save that already cleared the Opening. The same fault kept 29 quests of three other events from being offered, among them Shinra Building, 69th Floor - Exploration.
- The Dreadnought (INT to ELT) and the Realm of the Dragon King's explorations had no random battles, and The Crystal Tower's 2022 reruns had none on their upper floors. Their maps mark those tiles with encounter zones the server sent no battles for. They have them now.
- Pandemonium - Exploration does have random battles. Its map gives a 5% chance per step, and none for the first 20 steps on each floor, so a short walk can meet none.
- New settings `EXVIUS_CLEAR_SWITCHES` and `EXVIUS_ENCOUNTER_MAP_FIELDS` (see the README).

## 2026-11-13: Convert lists: the cause, and a way to get them

- Convert to Prism and Convert to Fragments are empty because the game never downloads the unit conversion table when it is opened fresh. The game only fetches that table if one of its own tables is already loaded when it builds its download list, and on a fresh start it isn't yet.
- Until this is automatic: after opening the game, go to Menu, choose to return to the title screen, and start again. The game then fetches the table and both lists work until the app is fully closed.
- The earlier updates that made the game "fetch the table once more" did nothing and are removed, with the `EXVIUS_REFETCH_TABLES` setting.
- With `EXVIUS_CLIENT_REPORTS` set to `1`, the server log says what the game's own log reports about that table (`docker compose logs server | grep CONVERT-TABLE`). The game uploads its log without asking or showing anything; a log it sends again is now saved only once.

## 2026-11-13: Step-up summon art

- A step-up summon showed its art on the first step and an empty frame on every later step. The art now stays on every step.
- New setting `EXVIUS_STEP_ART` (see the README).

## 2026-11-13: The Enchanted Maze, exploration fights

- The Enchanted Maze - INT and ADV: many of their fights had no enemies for the game to load, ADV's first room among them, which could close the game. They have their enemies now.
- The same is fixed in 85 other explorations (149 fights), such as Isaaru's Aeons, The Crystal Tower, Siren's Tower, Kilika Woods, Pandæmonium and Big Bridge - Exploration: the boss and set fights their maps start now have enemies.
- Two ADV fights ("EXP Lv4" and "GIL Lv4") have no surviving record. They use the quest's Lv5 fights as stand-ins.
- New setting `EXVIUS_SCENARIO_STAND_INS` (see the README).

## 2026-11-13: Bulk Fusion

- Bulk Fusion now fuses every unit you picked. Before, only the first unit's copies were fused and the rest came back.

## 2026-11-13: Summon screen download with all banners shown

- With `EXVIUS_SUMMON_ROTATION` set to `0`, opening the summon screen downloads the art of every banner, and the download stopped just before the end with "A connection error has occurred". One banner's art (the Hyoh / Veritas of the Frost featured summon) is a very tall picture, and the server failed every time it prepared it. While failing it asked for a very large amount of memory, which is the likely reason some servers restarted. Oversized art is now scaled down first, and a picture the server can't prepare is sent as it is instead of failing the download. Update, then open the summon screen again; what was already downloaded is kept.
- Twelve images with a ★ in their file name now go out under plain names. An earlier version of this entry gave them as the cause of the failed download. They weren't.
- If a download still fails, the server log says why: `docker compose logs server | grep -E "Traceback|BANNER-FIT|HTTP REFUSED"`.

## 2026-11-12: 5★ Select list, summon pools, drops, back-pay and exchange fixes

Every fix since the first release was tested again from end to end. These are the ones that didn't fully work, or broke something else, and are fixed now. Open the game twice after updating.

- The 5★ Select Summon's list now has the 80 limited and collaboration units added on 2026-11-10. That update never reached the game: the list stayed at 234 units.
- Weekly featured summons no longer give limited, collaboration or seasonal units they don't feature, and Gilgamesh (FFV) is in them. All of Global's launch units can be summoned from the start: Xiao, Cerius, Terra, Kuja, Garland, Zidane and Vivi were missing.
- The later summons of the replay (Global's 2022-24 banners) no longer give a unit's Brave Shift or awakened form as a separate unit.
- Raid box summons: "next box" no longer lists every summon in the game. The Drop Rates pages of box summons and of the 5★ Select Summon list what is really drawn. "Raid Summon: Destroy the Machine Lifeform" shows once.
- The esper Tests give 10 Supercite a clear (15 and 15 in each third test) and the Chamber of Enlightenment its Enlightenment Points (300 to 10,000), as on Global. They gave 1.
- Enemies in 15 quests that never dropped anything now drop, among them Grandshelt Castle - Throne Room, Lanzelt Ruins - Basement Lv. 1 and Zadehl Southersands - Lost City.
- Vow of the Revived Legend's "Lv. 7 - Burst Pots" stage gives its Burst Pot.
- If you leave a battle and start the same quest again, event currency and the Guide count the battle you fought, not the one you left.
- Town quests that finish at the end of a battle, or are given inside an exploration, are saved and paid.
- Missed first-clear rewards: a Trust Moogle, cactuar or pot is no longer left out because you already hold one of the same kind. One left out since 2026-11-11 can't be sent again.
- Treasure chest mail: a New Game no longer gets the previous save's chests, and the mail no longer includes a chest you never opened.
- Shop exchanges: the events' own ability materia and Guaranteed Tickets (160 items in 33 events) are in the Shop's exchange list again. Those events drop a little more currency per clear to match. Battle at the Borders' exchange can be bought with Hairpins. The Super Trust Moogle and Red Star Quartz exchanges no longer show before the replay reaches them.
- Awakening a 6★ Kevin with an Omniprism is refused: the game has no 7★ Kevin, and it added a broken unit.
- A saved party still loads after one of its units has been awakened. A party saved before such an awakening has to be saved again.
- The Guide no longer checks off a unit's Neo Vision form when you only hold its 7★ form.
- Kira: the abilities of his Trust reward and Vision Card have English names.
- Short Stories, Twelve Types Takedown and Advent of Purgatory get their later quests when the replay reaches them.
- Mana Mystery is open in the replay week of its Global dates (3 to 16 February 2017), not the week before as well. If it was in your Vortex and left with the "Replay runs" update, it comes back when your replay reaches that week.
- `convert-test --undo` goes back one run each time.
- New setting `EXVIUS_EVENT_RUN_QUESTS_TABLE` (see the README).

## 2026-11-12: Town quests stay done; Quest Report

- Town quests you've completed (in Mitra and every other town) are no longer offered again after you restart the game. Quests you completed before this update are fixed the first time you log in. Quests you're still on stay as they are.
- The Quest Report now lists your ongoing and cleared quests, and the Episode tab its quests.

## 2026-11-12: Summon screen download error

- Fixed the summon screen starting a data download that failed and sent the game back to the title. Summons whose art the server hadn't finished preparing now show a picture with the summon's name until the art is ready.
- If your game asked to re-download all data: update the server, then let the game re-download when it asks. Your save is on the server and isn't affected.
- Convert to Prism and Fragments: the server now logs whether the game asks for the conversion table. The game also fetches that table once more.

## 2026-11-12: Items used in battle stay used

- Potions and other items you use in a battle (won, lost or retired) now leave your item set and your bag for good. Before, the item set refilled after you restarted the game.
- If a battle uses up every item in your set, the server keeps your previous set rather than risk emptying it by mistake.

## 2026-11-12: Results EXP, item set, chests, Big Bridge

- The results screen no longer shows level-ups that didn't happen. It now counts up only the EXP each unit earned.
- Your battle item set (Potions, Antidotes and so on) is still there after you restart the game.
- Treasure chests holding equipment, materia or key items (the Green Beret in Lanzelt Highlands and others) now give their item. Chests like these you opened in the last few days arrive once by mail, if the server still has the record. Other unpaid chests should be closed again and pay when you open them now.
- The Big Bridge (Final Fantasy V event): five of its fixed fights, Gilgamesh included, had no enemy data, which could close the game. It now plays its 13 fixed battles, as on Global, with no extra random battles.
- Other explorations whose fixed fights or bosses had no enemy data now have it.
- New setting `EXVIUS_CHEST_BACKPAY` (see the README).

## 2026-11-12: Convert to Prism and Fragments

- NV units you got by NV awakening (Dark Fina, Lightning and the like) now show in Convert to Fragments.
- Convert to Prism now gives only the prism, and Convert to Fragments only the fragments. Before, both gave both.
- Which units each list shows, as on Global:
  - Convert to Prism lists units at 5★ or 6★ that have a prism. That's nearly every unit that starts at 5★, but only 10 units that start at 3★ or 4★, and those only once they reach 5★. A 4★ unit at 4★ and any 7★ unit are never listed.
  - Convert to Fragments lists units with NV fragments, and NV units.
  - Trust Coin and Gil conversion never list NV units.
- New setting `EXVIUS_NV_AWAKENED_FLAG` (see the README).
- Open the game twice after updating.

## 2026-11-12: Game data download location

- The game data is now downloaded from a copy hosted with this project. Rebuild to pick up the change (`docker compose build && docker compose up -d`); nothing downloads again, your installed data is unchanged.

## 2026-11-12: Yuffie, Ayaka and Elly banners

- Added three featured summons the replay was missing: Materia Hunter Yuffie (January 2023), Christmas 2022 Cheerful Caroler Ayaka, and Xenogears' Holy Mother Reborn Elly (December 2022). The 2017 Halloween summon now features its units.
- The Embracer of Duty Edgar summon (November 2022) shows once instead of twice.

## 2026-11-12: Replay runs, late banners

- With the historic replay, banners and events now stay up for their whole Global run, so long ones (weekly free summons, anniversary campaigns) last several weeks. Some weeks are busier than others.
- Added Global's banners from September 2023 to the end of service (about 200 new summons, many with estimated dates), and three missing earlier ones: Cloud Strife & Avalanche's Barret, Silent Knight Charlotte, and the FINAL FANTASY XI banner with Lady Shantotto.
- Units Global released later than we had dated them (such as Silent Knight Charlotte) now wait for their Global date in summon pools.
- New settings `EXVIUS_REPLAY_FULL_RUNS`, `EXVIUS_LATE_BANNERS` and `EXVIUS_LATE_UNCONFIRMED` (see the README).

## 2026-11-12: Friend 10x, LB EXP, Kira, Metal Gigantuar card, all banners

- The friend point Standard Summon has a 10x button: 10 units for 2,000 friend points.
- Clearing a quest now gives LB EXP to every unit in your party, as on Global: 100 per stamina, 250 per raid orb, 100 per weapon-enhancement orb. Losing or retiring gives none.
- Kira's abilities that showed no name in battle now have English names and descriptions.
- Fixed the game crashing when you view the Metal Gigantuar's Here! vision card in the VIP Shop (and other vision cards sold or won the same way).
- `EXVIUS_SUMMON_ROTATION` set to `0` now shows every banner at once and also turns the historic replay off. Change it in `docker-compose.yml`, then run `docker compose up -d` (see the README).
- Open the game twice after updating.

## 2026-11-11: Omniprism

- Awakening a 6★ unit to 7★ with an Omniprism now works. Before, the server only accepted the unit's own prism and refused the awakening.

## 2026-11-11: NV awakening

- NV awakening no longer needs level 120 or 100% Super Trust, as on Global since Version 7.0.0 (March 2022). It still costs its materials and Gil.
- If an awakening can't be completed, the game now shows a message saying why instead of crashing in the awakening animation. Nothing is used.

## 2026-11-11: Convert table, Chamber of Riches Gil

- Correction to the previous entry: the Convert to Prism and Convert to Fragments lists also need a game table the game never loaded on iPhone. The game now downloads it again; open the game twice after updating.
- Quests now pay their own clear Gil. The Chamber of Riches pays almost all its Gil this way (1,500 to 85,000 per run), so it paid nothing before. Runs before this update aren't paid back.

## 2026-11-11: Farplane intro, Convert screen

- Fixed every way into the Farplane (the monuments, or walking from King Mog's area to the Tower of Earth) replaying the first Farplane scene and sending you back to Mitra. Open the game twice after updating. Two lost Farplane scenes (the Crest scene and the end of the Moogle quests) stay left out.
- Convert to Prism, Convert to Fragments and Trust Coin conversion list your units again, NV units included. This was fixed by the Guide update earlier today.

## 2026-11-11: Missed first-clear rewards

- First-clear rewards (Lapis, items, units) for quests you cleared but were never paid for now arrive by mail the next time you start the game, once per quest. Rewards you already got aren't sent again. To turn this off, set `EXVIUS_FIRST_CLEAR_MISSED` to `0` (see the README).

## 2026-11-11: Chamber drops

- The always-open chambers now drop what they dropped on Global: Holy Crystal and Sacred Crystal in the Chamber of Awakening, and the missing items in the Chambers of Crystals, Crysts, Forticite, Enlightenment and Creation and the esper Tests. The 5★ Chamber of Awakening also has its rare drops (Calamity Gem and others) at a low rate.

## 2026-11-11: Unit search, NV summons, pots

- Fixed the unit search finding nothing ("No displayable units"). It only lists units the Guide knows about, and the Guide was empty until the previous update; with that update, searching for a unit's name works. The Vision Card search now also finds cards by their English names.
- Pulling a Neo Vision unit now plays the Neo Vision summon animation instead of the treasure-chest one.
- Fixed unit pots from battles (for example Reno's pots in The Youngest Turk in History) never arriving. They now go to the unit's enhancement points.

## 2026-11-11: Farplane Tower of Earth gifts

- If you beat a Tower of Earth boss in the Farplane (White Dragon, Demon Chimera, Brachiosaur, Erinyes) but never got its gift (Murasame, Force Armor, Killer Bow, Apollo Harp), it now arrives by mail the next time you start the game. Gifts you already have aren't sent again.

## 2026-11-11: Story recipes, the Guide

- Fixed recipes the story gives never unlocking: the crafting tutorial's Bronze Knife recipe (with 3 Copper Ore) now comes after Earth Shrine - Exit, and the Magic Key recipe with the first clear of Grandshelt Castle - Throne Room. If you're already past those points, they arrive by mail the next time you start the game.
- The Guide now checks off units, items, equipment, materia and Vision Cards you have, including the lower forms of units you've awakened (for example 2★ Rain and Lasswell). Monsters are checked off from battles you fight from now on, with their knockdown counts and Libra scans. Units and items you sold or used up before this update can't be recovered.

## 2026-11-11: Daily summons, Mana Mystery shop

- Fixed once-a-day summons (such as the Lunar New Year free summon) showing a pull available again in the evening after you'd used it. The day now resets at 04:00 UTC (11 pm New York time in winter), like the server's other daily resets, and the summon screen shows it the same way.
- Fixed "A connection error has occurred" when buying Aura Glove or Ninja's Trump in the Mana Mystery (Secret of Mana) shop. Both can be bought now, and they also show in the Shop's exchange list. Every other exchange item was checked and buys fine.

## 2026-11-10: Free summons after ticket summons, extra ticket banners

- Fixed a free daily summon (such as Celebrating Lunar New Year) showing a white crystal and giving nothing after you'd used a ticket summon. The game was still naming the last ticket you used; the server now ignores a ticket the summon doesn't take, and a free summon never uses up a ticket.
- A summon that fails no longer shows "Already Summoned" when it wasn't counted.
- Holding a ticket now only adds that ticket's own summon. The 2019 "5★ Select Ticket Lapis Summon" no longer appears in Limited Time, and summons that were listed twice (NV Guaranteed EX Summon, Bonus Present Ticket Summon) show once.

## 2026-11-10: More units in the 5★ Select Summon

- The 5★ Select Summon now also offers Global's limited and collaboration 5★ units (80 more, such as 2B, Sora, Edward Elric and Lilith), at the same 10 tickets. Open the game twice so it picks up the new list.

## 2026-11-10: 5★ Select Summon works

- Fixed the 5★ Select Summon's "Ticket Summon" button doing nothing. It now opens the unit list; pick a unit and 10 5★ Select tickets are spent on it.
- The 5★ Select Summon shows its animated field again.

## 2026-11-10: Ticket summons show up

- Fixed bought summon tickets with no summon to use them on, such as the 1/10 NV Summon Tickets from the VIP Shop. While you hold them, NV Guaranteed EX Summon shows on the summon screen; one summon takes 10 tickets. The same fix covers the 5★ Select, Arena and 5+1 ticket summons.
- Summon tickets aren't listed under Items. They show on the summon that uses them, with how many you have.

## 2026-11-10: Mana Mystery listed once

- Mana Mystery now lists its five quests once instead of twice. The second set (same stages, double mission Lapis) is gone. Producer of the Crystal is now a single quest.
- If you cleared quests in Mana Mystery's second set, the matching quests in the remaining set pay their first-clear rewards again.

## 2026-11-10: Copied quests removed

- Events that listed the same quest several times now list it once: Chamber of Challenges (each area went from up to 110 quests to 20), Elemental Turn Challenge and Producer of the Crystal. Only exact copies were removed: same battle, missions and rewards.

## 2026-11-10: Event currency on every event quest

- Fixed event currency never dropping in some event quests, such as Mana Mystery's second set of quests (its ELT included). 103 quests in 18 events had no currency drops; their monsters now drop it, about as much as the event's other quests of the same level.

## 2026-11-10: Event currency from battles

- Fixed event currency from enemies (such as Candy in Mana Mystery) not arriving. If the game doesn't count the currency the enemies dropped, the server now adds it at the end of the battle, so every clear pays it.

## 2026-11-10: Vision Cards, Aquapolis hidden

- Vision Cards equipped on Neo Vision units (such as Blade of Vengeance Ibara) now stay equipped; before, the slot looked empty. Loading a saved party no longer takes units' Vision Cards off.
- Memories from the Aquapolis is hidden from the Vortex for now: its stage files were lost, so it had no treasure chests and no proper ending.
- A summoned Neo Vision unit now comes with a random Vision Card from the cards Global had in its summon pool at that point in the replay, like in Global. A unit's own card comes from EX awakening (EX+1 and EX+3), as before.

## 2026-11-10: Faster loading

- The game loads faster: the server no longer asks it to upload its error log over and over (about 22 MB every 15 seconds). Uploads are now off by default; when you turn them on to get a log, the game sends it once per launch. See the README ("Logs from the game itself").

## 2026-11-10: Exchanges follow the replay, unit dates, the Captain

- King Mog and the Mog Minister now trade for the event that is on this week, like in Global (for example Candy during Mana Mystery), instead of always Star Quartz and Auracite Shards. Between events they keep the exchange of an event currency you still have.
- Exchanges on the Shop's summon coin screen show up while their event is on or while you hold their currency. The Star Quartz unit exchanges appear when the replay reaches January 2023, when Global added them.
- Events only show the quests they had at that point in the replay. Trials and stages a later run added (for example Chamber of the Vengeful's later trials) appear when the replay reaches them, so their rewards and exchanges no longer show up early.
- Orbonne Monastery Vaults' enemies drop Auracite Shards while the event is on, for the Mog Minister's exchange.
- The Vortex lists story and limited-time events at the top and the farming chambers at the bottom.
- Fixed units showing up in summons later than they came out on Global, such as Gilgamesh (FFV), who now appears from the start. 187 units' release dates were checked against Global's own history and moved earlier.
- The units Global launched with can be summoned from the start, including Roselia, Miyuki, Gilbert, Xiao, Firion, Maria, Vaan, Penelo, Shantotto and Fran.
- Limited-time, collaboration and seasonal units no longer show up in regular summons. Like in Global, they only come from the summons that feature them.
- The Moogle Guard Captain in the Vortex town now trades for leftover event currency: his menu lists the exchanges for currency you still hold that King Mog and the Mog Minister aren't showing this week, plus his own Super Trust Moogle and Dark Visions exchanges once the replay reaches them. Future and empty exchanges are gone. His menu updates each time you start the game.
- Exchanges now show the name of the merchant you opened them from: the Mog Minister no longer says he's King Mog, and the Captain's exchanges show the Captain.
- The Vortex town is no longer downloaded again every time you enter it.
- The Captain's exchanges show the right currency icon instead of a Star Quartz-like crystal.
- The Shop's exchange list and King Mog, the Mog Minister and the Captain now share one stock: an item limited to 2 can be bought twice in total, like in Global, not twice in each place.
- Unit pictures on the News notices and the summon Drop Rates pages now come from the game's own files instead of the Brave Exvius wiki, so Neo Vision and other 7★ units (Sol -Neo Vision-, Summoner Yuna, Sora (KHIII) and more) show a picture instead of a grey box.

## 2026-11-10: Collection points

- Collection points in explorations now show up (the sparkling spots; Dalnakya Cavern has three) and give what they gave in Global: ore, Lumber, crysts or magicite, or the event's own items in event explorations.
- What you collect shows on the result screen and lands in your bag when you leave the exploration.

## 2026-11-10: Story units

- Story units (Rain, Lasswell, Fina, Lid, Nichol, Sakura, Jake) and event reward units no longer show up in normal summons.
- Story units now join as you reach them in the story. Saves already past that point get them at the next login.
- Extra copies of story units you already pulled can be sold now.

## 2026-11-10: Random battles, drops, first-clear rewards

- Random battles are actually random now. Chamber of Awakening 5★ was only ever dropping Hard Rocks and Fury Seeds because of this, along with about 1,300 other quests.
- Enemy drop tables filled in from Global's records, so some quests that dropped nothing now drop stuff.
- Event currency (Candy etc.) drops in battle like it used to, boosted since there are no packs to buy.
- King Mog exchange shops are back.
- First clear rewards actually pay out now. If you've already cleared quests, check your gift box for a "First-Clear Rewards" mail.
- Some event rewards corrected to match Global's original runs, and missing challenges restored.
- Raid summons and box summons added. They show up when the replay reaches each raid.
- Fixed the Windows / Docker Desktop `exec /app/entrypoint.sh: no such file or directory` error.
