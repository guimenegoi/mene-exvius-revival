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

Each entry is one update to this repo. To update: in your repo folder run `git pull`, then from `ios-server` run `docker compose build && docker compose up -d`. Your save isn't touched. Open the game twice afterwards so it picks up the new data.

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
