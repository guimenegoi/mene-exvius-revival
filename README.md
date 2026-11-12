# Exvius Revival for iOS

> **Fork experimental para Android:** este repositório também acompanha a adaptação do
> cliente FFBE Global 9.1.0 e a pesquisa para executar o backend no próprio Android.
> Veja **[Estado dos testes, arquitetura e próximos passos](docs/ANDROID.md)**.
> **O guia abaixo é o README original do upstream, para iOS; não descreve um
> instalador Android pronto.**

Play **Final Fantasy Brave Exvius** (Global) on an iPhone again, with the **unmodified App Store app**, against a game server you run yourself.

This project runs the [Exvius Offline](https://github.com/Elvlin/exvius-offline) game engine as a server in Docker. The iPhone app thinks it's talking to the original servers. Nothing on the phone is modified apart from trusting one private certificate.

It also adds a **historical replay**: summons, Vortex events and shops follow Global's own release history, starting at Noctis's December 2016 banner and moving three historical weeks per real week (two per week from the first Neo Vision banner in August 2020). The permanent summons only draw units that had come out by then, holiday banners arrive the week before each real holiday, and a "This week" notice on the News board lists what just arrived, and the home screen banners show that week's events. The week changes on Sunday at 10 PM US Eastern by default. With the replay off, banners rotate randomly every week instead.

> Tested with the Global app at build 1167 (`ver.9100`) on an iPhone 17 Pro running iOS 27, with the server on an Unraid NAS. The same Docker setup is meant to run on any computer that runs Docker.

---

## What you need

- **The app on your iPhone.** FFBE is no longer in the App Store, but if your Apple account ever downloaded it, it's under **App Store → your account → Purchased**.
- **A computer to run the server**, on whenever you want to play. The default below is a Windows, Mac or Linux PC with **Docker Desktop**. A NAS or home server works the same way (see [Other hosts](#other-hosts)).
- **About 17 GB of free disk space** during setup, 15 GB afterwards.
- **A free [Tailscale](https://tailscale.com) account.** Tailscale connects the phone to the server, at home or away, without opening anything on your router. You install the Tailscale app **on your iPhone only**; the server brings its own copy.

## Quick start

The whole setup in order, one action per step. Each part links to the full instructions in [Setup](#setup) if you get stuck.

**On the computer that will run the server**

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/), open it, and leave it running.
2. Make a folder called `exvius` and put this repository in it as `exvius/repo` ([details](#1-install-docker-and-get-the-files)).
3. Open a terminal in `exvius/repo/ios-server`.
   - **Windows:** open that folder in File Explorer, click the address bar, type `powershell` and press Enter.
   - **macOS:** open **Terminal**, type `cd ` (with a space), drag the `ios-server` folder into the window, and press Enter.
   - **Linux:** `cd` into the folder.

**In Tailscale (on the website)**

4. Create a free account at [tailscale.com](https://tailscale.com).
5. In the [admin console](https://login.tailscale.com/admin), go to **Settings → Keys → Generate auth key** and copy the key ([details](#2-tailscale)).
6. In the terminal, run `cp .env.example .env`, open `.env` in a text editor, paste the key after `TS_AUTHKEY=` and save.

> **You don't install Tailscale on the computer.** The server's container runs its own copy and joins your Tailscale account by itself as a machine called `ffbe`. If the computer already has Tailscale, that's fine; the container shows up as a separate machine.

**Back in the terminal**

7. Run these one at a time, waiting for each to finish:

   ```bash
   docker compose build
   ```

   ```bash
   docker compose run --rm server fetch-data
   ```

   ```bash
   docker compose up -d
   ```

   The second one downloads about 14.6 GB and takes a while. If it stops, run it again; it picks up where it left off.
8. Run `docker compose logs -f server` and wait for a line ending in `http://100.x.y.z/ca.mobileconfig`. Write down that `100.x.y.z` address, then press Ctrl+C. The server keeps running.

**In the Tailscale admin console**

9. **Machines → ffbe → ⋯ → Disable key expiry.**
10. **DNS → Nameservers → Add nameserver → Custom.** Enter the `100.x.y.z` address, turn on **Restrict to domain**, enter `gumi.sg`, and save.
11. Add one more nameserver the same way, with the same address, restricted to `exvius.com` ([details](#5-tailscale-admin-console)).

**On your iPhone**

12. Install **Tailscale** from the App Store, sign in with the same account, and turn it on.
13. Install **FFBE** from **App Store → your account → Purchased**.
14. In **Safari**, open `http://100.x.y.z/ca.mobileconfig` (your address) and tap **Allow**.
15. **Settings → Profile Downloaded → Install.**
16. **Settings → General → About → Certificate Trust Settings** → turn on **Exvius Offline Root**. The game won't connect without this ([details](#6-iphone-trust-the-certificate)).
17. Open the game and let it download. After you've logged in once, close the game fully (swipe it away) and open it again ([why](#7-play)).

**Every time you play:** the computer is on with Docker running, and Tailscale is turned on on the phone.

## How it works

```
iPhone (stock FFBE app, Tailscale on)
   │  "where is v900-lapis.gumi.sg?"
   ▼
Tailscale split DNS ── only gumi.sg / exvius.com questions ──▶  ffbe (your server's own Tailscale address)
   │                                                               ├─ DNS: answers gumi.sg / exvius.com with its own address
   │  HTTPS to v900-lapis.gumi.sg                                  ├─ HTTPS 443: game API and game file downloads
   └──────────────────────────────────────────────────────────▶  └─ HTTP 80: the certificate profile for the phone
```

- **Its own Tailscale address.** One container, `ffbe`, runs Tailscale (joining your tailnet as a machine called `ffbe`) and the game server together. If either stops, both restart together. Nothing listens on your computer's own ports, so it can't clash with anything else you run.
- **A tiny DNS responder.** It answers only `gumi.sg` and `exvius.com` names. A Tailscale split-DNS rule sends the phone's lookups for those names to it. Nothing else about your phone's or tailnet's DNS changes.
- **A private certificate** that can only vouch for `gumi.sg` and `exvius.com` (an X.509 name constraint). You install it on the phone once, and it can't be used for any other site.
- **The game data** (about 14.6 GB) is downloaded from the Exvius Offline GitHub releases during setup.

Everything the stack creates lives in one folder (`FFBE_DIR`). [Removing everything](#removing-everything) is at the end.

---

## Setup

The commands are the same on Windows (PowerShell), macOS (Terminal) and Linux unless noted.

### 1. Install Docker and get the files

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) and start it. On Linux, Docker Engine with the Compose plugin also works.
2. Make a folder for everything, for example `exvius` in your home folder, and download this repository into it as `repo`:

   ```bash
   mkdir exvius
   cd exvius
   git clone https://github.com/CreamySeaman6/Exvius-revival-ios.git repo
   cd repo/ios-server
   ```

   If you don't have `git`, download the repository from GitHub (**Code → Download ZIP**) and unzip it so that the files are in `exvius/repo`.

All the remaining commands run from `exvius/repo/ios-server`.

### 2. Tailscale

1. Create a Tailscale account, then install the **Tailscale** app on your iPhone and sign in with the same account.
2. In the [Tailscale admin console](https://login.tailscale.com/admin), go to **Settings → Keys → Generate auth key**. Leave it **not** reusable and **not** ephemeral. Copy the key.
3. Create the settings file (this works on Windows, macOS and Linux):

   ```bash
   cp .env.example .env
   ```

4. Open `.env` in a text editor with the command for your system, paste the key after `TS_AUTHKEY=`, and save:
   - Windows: `notepad .env`
   - macOS: `open -e .env`
   - Linux: `nano .env`

   Leave `FFBE_DIR=../..` as it is to keep the data in your `exvius` folder, or set any other path.

The key is only used on the first start. It stays on your computer in `.env`, which git ignores, so it's never uploaded anywhere.

You don't install Tailscale on the computer itself. The container runs its own copy and uses this key to join your Tailscale account as a machine called `ffbe`. If the computer already runs Tailscale, that's fine; the two don't interfere.

### 3. Build and download the game data

```bash
docker compose build
docker compose run --rm server fetch-data
```

`fetch-data` downloads about **14.6 GB**, checks every pack, unpacks it and deletes the download. If it stops for any reason, run it again; it picks up where it left off.

This also starts Tailscale for the first time, so a machine called `ffbe` appears in your Tailscale admin console.

### 4. Start the server

```bash
docker compose up -d
docker compose logs -f server
```

Wait for a line like:

```
[ios-server] ready. Certificate profile for the phone: http://100.x.y.z/ca.mobileconfig
```

Note that `100.x.y.z` address, then press Ctrl+C to stop watching the logs. The server keeps running in the background.

### 5. Tailscale admin console

1. **Machines → ffbe → ⋯ → Disable key expiry.** Otherwise the server drops off your tailnet after about six months.
2. **DNS → Nameservers → Add nameserver → Custom.**
   - Nameserver: the `100.x.y.z` address from step 4.
   - Turn on **Restrict to domain** and enter `gumi.sg`.
   - Save.
3. Add a second nameserver entry the same way, with the same address, restricted to `exvius.com`. It covers the game's notice pages: optional, but it makes those requests fail fast instead of hanging.

If you use custom Tailscale access rules, the phone must be allowed to reach `ffbe` on TCP 80 and 443 and UDP 53. The default policy already allows that.

### 6. iPhone: trust the certificate

1. In the Tailscale app, make sure you're connected and **Use Tailscale DNS settings** is on (it is by default).
2. In **Safari**, open `http://100.x.y.z/ca.mobileconfig` and tap **Allow**.
3. Open **Settings → Profile Downloaded → Install.** It's listed as "Exvius Offline server" and says "Not Verified". That's normal for a private certificate.
4. Open **Settings → General → About → Certificate Trust Settings** and turn on **Exvius Offline Root**. This step is easy to miss, and the game won't connect without it.
5. Test it in Safari: open `https://v900-lapis.gumi.sg/__exvius/hello`. A page saying **"Reachable. You can open the game."**, with no warning, means DNS and the certificate both work.

### 7. Play

1. Open the game. The first launch downloads the game's data from your server; keep the app open until it finishes.
2. After you've logged in once, **close the game fully and open it again** (swipe it away in the app switcher). The server's patched download lists only reach the phone during login, after the game has already decided what to fetch up front, so the second launch is the one that gets them. Without it, the first battle can crash.
3. Music downloads in the background. Until a track has arrived, that scene plays without music; sound effects still work. Leaving the game open on a menu for 10–15 minutes lets it catch up.

---

## Other hosts

The stack is plain Docker Compose, so it runs anywhere Docker does. A machine that's always on (a NAS or home server) means you can play any time without your PC being on.

- **Linux server:** same steps. Install Docker Engine and the Compose plugin.
- **Unraid:** follow the same steps in the Unraid terminal (Compose comes with the **Docker Compose Manager** plugin from the Apps tab), with `FFBE_DIR` set to `/mnt/user/appdata/ffbe` and the repo cloned to `/mnt/user/appdata/ffbe/repo`. Then move the container into the Docker tab ([below](#unraid-run-it-from-the-docker-tab)).
- **Synology and other NAS systems:** need Docker (Container Manager) and SSH access to run `docker compose`. The container needs `/dev/net/tun` for Tailscale, which some NAS systems only provide after enabling it.

### Unraid: run it from the Docker tab

Started with `docker compose up`, the container shows in the Docker tab but Unraid doesn't manage it: no Autostart switch, no Edit, and backup plugins don't know how to bring it back. `unraid/my-ffbe.xml` is an Unraid template for the same container (same image, folders, Tailscale sign-in and settings), so Unraid manages it like any other app.

1. In the Unraid terminal, build the image and remove the Compose-run container (your save, the data and the Tailscale sign-in stay in `FFBE_DIR`):

   ```bash
   cd /mnt/user/appdata/ffbe/repo/ios-server
   grep FFBE_DIR .env
   docker compose build
   docker compose down
   cp unraid/my-ffbe.xml /boot/config/plugins/dockerMan/templates-user/my-ffbe.xml
   ```

   The template assumes `FFBE_DIR` is `/mnt/user/appdata/ffbe` (the `grep` line shows yours). If `FFBE_DIR` is something else, change the three folder paths in step 2.
2. **Docker** tab → **Add Container** → **Template** → under *User templates*, pick **ffbe**. Leave `TS_AUTHKEY` empty (the Tailscale folder is already signed in) and select **Apply**.
3. Turn on **Autostart** for `ffbe`. It now starts after a reboot, and backup plugins stop and start it like any other container.
4. Check it: the `ffbe` icon → **Logs** should show `Tailscale state: Running`, then the server starting.

From then on, don't run `docker compose up` (it would make a second container with the same name). `docker compose build` and `docker compose run --rm server fetch-data` are still fine. Settings are in the container's **Edit** page instead of `docker-compose.yml`.

**Updating** on Unraid:

```bash
cd /mnt/user/appdata/ffbe/repo && git pull
cd ios-server && docker compose build
```

Then **Docker** tab → `ffbe` → **Edit** → **Apply**: that recreates the container from the new image with your settings. (**Restart** keeps the old image.) Unraid shows the image's update status as "not available" because it's built locally; that's expected.

When a new version adds settings, the notes will say so: add them on the Edit page with **Add another Path, Port, Variable, Label or Device**. Copying the template file again would reset your own changes.

---

## If it doesn't work

Watch the server while you open the game:

```bash
docker compose logs -f server
```

| What you see | What it means |
| --- | --- |
| Nothing at all when the game starts | The phone isn't reaching the server. Re-check step 5, and that the hello page in step 6 loads. |
| `TLS handshake failed from 100.…` | The phone doesn't trust the certificate. Check **Certificate Trust Settings** (step 6.4). |
| `OK POST …` lines | The game is talking to the server. |
| `CDN GET … -> 404` | The game asked for a file the server doesn't have. A few of these are normal; a long run of them during the first download is worth reporting. |
| The game crashes when the first battle starts | Close it fully and open it again (step 7.2). |
| A scene has no music | That track hasn't downloaded yet (step 7.3). |

**Logs from the game itself.** iOS hides apps' logs, but the game can upload its own error log to the server. This is off by default, since each upload is tens of MB. While it's on, the game uploads its log once each time you open it. Turn it on when you need a log: set `EXVIUS_CLIENT_REPORTS: "1"` in `docker-compose.yml` (on Unraid, the `EXVIUS_CLIENT_REPORTS` variable in the template), run `docker compose up -d`, open the game and repeat what went wrong, then open the game once more. Each upload is saved in `FFBE_DIR/server/client-reports/`, and the server log shows a `CLIENT REPORT` line when one arrives. Set it back to `"0"` afterwards. To read one:

```bash
pip install cryptography
python3 devtools/decode_reports.py FFBE_DIR/server/client-reports/<file>.txt
```

The server also keeps a record of each request it received, for three days and at most 300 MB, in `FFBE_DIR/server/requests/` (see [Disk use](#settings)).

---

## Known issues

- **Memories from the Aquapolis** (a 2017 exploration event) is hidden from the Vortex. Its stage files (each stage's boundaries, boss and ending, and its treasure chests) were lost from the game data, so every stage was the whole map with no chests and no proper ending. `EXVIUS_HIDDEN_EVENTS: "0"` shows it again (see [Settings](#settings)).

## Everyday use

| Task | Command |
| --- | --- |
| See this week's banners | `docker compose exec server python3 /app/ffbe.py rotation` |
| See the next four weeks | `docker compose exec server python3 /app/ffbe.py rotation 4` |
| Restart the replay from its start date | delete `FFBE_DIR/server/state/replay.json`, then `docker compose restart server` |
| Show the save's status | `docker compose exec server python3 /app/ffbe.py status` |
| Restart | `docker compose restart server` |
| Logs | `docker compose logs -f server` |
| Stop | `docker compose down` |
| Unraid | After [moving it to the Docker tab](#unraid-run-it-from-the-docker-tab): start, stop, restart, logs and settings are all on the `ffbe` icon. Commands run inside it with `docker exec ffbe python3 /app/ffbe.py …` (for example `rotation` or `status`) instead of `docker compose exec server …`. |
| Start the game over | `docker compose exec server python3 /app/ffbe.py new-game --yes` (the old save is backed up to `server/state/backups/`) |

**Your save** is in `FFBE_DIR/server/state/`. Back up that folder.

**Certificates** are in `FFBE_DIR/server/certs/`. They're made on your computer the first time the server starts and never leave it.

- The root certificate on your phone lasts ten years.
- The server certificate lasts about 13 months and renews itself; the container restarts once to do it.
- If you delete the `certs` folder, install the phone profile again (step 6).

**Updating** to a newer version:

```bash
git pull
docker compose build
docker compose run --rm server fetch-data   # only downloads data packs that changed
docker compose up -d
```

## Settings

Settings are environment variables in `docker-compose.yml`. After changing one, run `docker compose up -d`.

**Disk use**

The server keeps its own records for troubleshooting and trims them every hour, so its folder stays small. Your save, the certificates and the downloaded game data are never touched.

| Setting | What it controls |
| --- | --- |
| `FFBE_REQUEST_LOG_DAYS` | Request records (`server/requests/`, one per game request) older than this many days are deleted. Default `3`. |
| `FFBE_REQUEST_LOG_MB` | Request records are also trimmed, oldest first, to stay under this many MB in total. Default `300`. |
| `EXVIUS_CLIENT_REPORTS` | `0` (default) doesn't ask the game for its error log; a log the game already has queued is answered but not saved (the server log shows its size). `1` asks the game to upload its log and saves each upload in `server/client-reports/`, for troubleshooting: while it's on, the game uploads its log (tens of MB) once each time you open it. See "Logs from the game itself" in [If it doesn't work](#if-it-doesnt-work). |
| `FFBE_CLIENT_REPORTS_KEEP` | How many of the game's uploaded logs (`server/client-reports/`, up to tens of MB each, only while `EXVIUS_CLIENT_REPORTS` is `1`) to keep, newest first. Default `30`. |

The container's own log (`docker logs ffbe`) is capped at 60 MB by Docker (3 files of 20 MB).

**Historical replay**

| Setting | What it controls |
| --- | --- |
| `EXVIUS_REPLAY` | `1` (default) follows Global's history: each week shows the summon sets released in that week's slice of history, the Vortex events that launched with them, and permanent summons and exchange shops limited to units released by then (NV EXVIUS appears with the NV era). `0` uses the random weekly rotation below. Needs `EXVIUS_SUMMON_ROTATION=1`. |
| `EXVIUS_REPLAY_START` | Where history starts in your first replay week. Default `2016-12-16` (Noctis). |
| `EXVIUS_REPLAY_PACE` | Historical weeks per real week, with optional changes by date. Default `3,2@2020-08-20`: three, then two from Global's first Neo Vision banner. |
| `EXVIUS_REPLAY_NV_ERA` | When NV EXVIUS appears among the permanent summons. Default `2020-08-20`. |
| `EXVIUS_REPLAY_NOTICES` | `1` (default) adds a "This week" notice to the News board for each replay week, listing its summons, its deal summons (with what each deal offers), Shop bundles that go on sale that week, mails sent that week, and its Vortex events. `EXVIUS_REPLAY_NOTICE_WEEKS` (default `8`) is how many weeks stay listed. |
| `EXVIUS_NOTICE_ART` | `1` (default) shows each unit's picture on the News notices and the summon Drop Rates pages, taken from the game's own unit files (nothing is downloaded): when the server starts it copies the pictures out of `FFBE_DIR/data/native/common_lang/sd/unit/` into `FFBE_DIR/server/ios-cache/notice-art/` in the background (about 3,700 pictures, under 20 MB; it takes a second or two, and pages opened before that read the picture straight from the game files). Delete that folder to have them copied again. A unit with no picture in the game data gets a blank space. Summon and event banners come from your own data, except the banners of the events added in `source/server/event_history.json`: the server downloads those from the wiki once at startup into `FFBE_DIR/data/native/en/sd/area/` (until then their Vortex tiles show the default picture). `0` shows unit names without pictures. |
| `EXVIUS_REPLAY_FULL_POOL` | Summons paid only with a ticket you can't buy over and over (the Early Bird's Guaranteed NV Summon Ticket, the once-only SP NV tickets, event and login tickets) ignore the replay's unit limit, so a held ticket is a real one-off chance at any unit, NV included. Tickets the Shop sells without limit keep the limit. This setting names more banners by id (default `9200107,9200108`). Ticket-paid banners appear on the summon screen whenever you hold the ticket. |
| `EXVIUS_REPLAY_MARQUEE` | `1` (default) fills the home screen's banner strip with the original banners of this week's Vortex events (the same art as the Vortex tiles, at most `EXVIUS_REPLAY_MARQUEE_MAX`, default `6`). Needs `MARQUEE_FLAG=1`, which turns the strip on; set `MARQUEE_FLAG` to `0` if the home screen misbehaves. Weeks with no dated events show no banners. Tapping a banner opens that event's stages; if the game doesn't find the event it opens the Vortex instead. |
| `EXVIUS_REPLAY_MARQUEE_TAP` | `1` (default) makes a home banner open its event's stages when tapped. `0` makes every banner open the Vortex, as before. Clash of Wills and Dark Visions banners always open the Vortex. |

Your first replay week is recorded in `FFBE_DIR/server/state/replay.json`. Changing the pace later re-times the whole replay from that week. Units you already own stay in your save. Holiday sets come out of the timeline and appear in the week before each real holiday and the holiday's own week. Each holiday brings the next original year that hasn't been shown (if it's less than a year ahead of history), plus any years the replay went past, older ones first. When history runs out, the random rotation takes over with every unit.

**Earned Lapis**

The original game's Lapis income assumed you'd buy Lapis. These settings raise what you earn by playing (Shop purchases are never touched). With the defaults, a story mission's challenges pay about 250 Lapis, a full day of daily quests pays 3,250 Lapis, and every week brings a 10+1's worth of summon tickets.

| Setting | What it controls |
| --- | --- |
| `EXVIUS_LAPIS_MULTIPLIER` | Multiplies every Lapis amount earned by playing: mission challenges, event repeats, rank-ups, login and catch-up mails, quests, daily quests. Default `5` (a story mission's challenges, 50 Lapis in the original, pay 250); `1` is the stock game. The challenge screen still shows the original amounts. |
| `EXVIUS_DAILY_QUEST_LAPIS` | Lapis paid by each daily quest (before the multiplier). Default `150`. `0` keeps the old gil/Lapis mix. |
| `EXVIUS_DAILY_ALL_BONUS` | Extra Lapis for finishing all of a day's daily quests (before the multiplier). Default `200`. |
| `EXVIUS_DAILY_CUSTOM` | `1` (default) adds custom daily quests to the original ones: story and Vortex clears, Limit Bursts, spells, Espers, clears with no KOs, trust gains, unit levels, fusions, expeditions, Arena wins, summons and Gil. Each day draws a different mix, never two of the same kind. Their rewards change from day to day: Lapis (up to 2,500), Gil, Rare Summon Tickets, NRG Restores, Metal Cactuars and Gigantuars, Trust Moogles (5% or 10%), and now and then a Guaranteed Ticket. The quests and reward lists are in `source/server/daily_quests_custom.json`. `0` serves only the original daily quests. Lapis rewards now show the amount actually paid (after the multiplier). |
| `EXVIUS_DAILY_QUEST_COUNT` | Daily quests per day while the custom ones are on. Default `5`. |
| `EXVIUS_CALAMITY_WRIT_DROP` | Percent chance that an enemy also drops a Calamity Writ (an awakening material no enemy drops in the original game; it came only from events). Every enemy in a battle and every exploration battle rolls once. Default `0.5`, about one Writ per 20 story missions. `0` turns it off. |
| `EXVIUS_BATTLE_LOTTERY` | `1` (default) rolls each battle wave's enemies every time you start a quest, from the groups the game's tables list for that wave and at their odds, so repeat runs meet different enemies and get those enemies' drops (e.g. Chamber of Awakening's waves pick from 7 groups). `0` always serves the most likely group, as before 2026-11-10. |
| `EXVIUS_GLOBAL_DROPS` | `1` (default) uses enemy drop lists checked against Global's record (the FFBE wiki): story quests keep Japan's drops and add the items the wiki lists that Japan's don't; quests that dropped nothing now drop what the wiki lists for their monsters; event quests that had drops keep them. Event currencies are handled separately (see `EXVIUS_EVENT_CURRENCY_RUNS`). Details: `ios-server/research/DROP_CHECK.md`. `0` serves the old lists. |
| `EXVIUS_CURRENCY_BACKSTOP` | `1` (default): when a cleared battle's enemies dropped event currency (such as Candy) that the game didn't report at the end, the server pays the missing amount itself and adds it to the result, so it always arrives. The server log shows `bundle dropped ... phone reported ...` for each such clear. `0` pays only what the game reports. |
| `EXVIUS_WIKI_DROP_RATE` | Percent chance for each of those wiki-only drops (the wiki records no rates). Default `30`, Japan's most common rate. `0` leaves them out. In `docker-compose.yml`. |
| `EXVIUS_WIKI_REWARDS` | `1` (default) pays the FFBE wiki's first-clear and challenge rewards where they differ from Global's final data and nothing else settles it (37 events, e.g. Esper of Destruction's 100 Lapis first clears; events Global ran twice use them in their first run's week), and brings back 64 challenges Global's final data dropped (Chamber of Supercite's esper trials, Sprouts of Devouring, Esper of Destruction, The Fighting Pits). The challenge list and first-clear rewards the game shows match. List: `ios-server/research/REWARD_OVERRIDES.md`. `0` turns it off. |
| `GACHA_DEALS` | The deal summons Global ran from 2018 on (step-ups with items and discounts, once-per-player free 10+1s, free daily summons, rate-ups and the rest), each on its real date in the replay. Default `1`; `0` leaves them out. |
| `EXVIUS_STORY_UNITS` | `1` (default) has the story characters join when the story reaches them, as in Global: Fina after Lechios Hills (at level 20), Lid after Galebreak, Nichol after the Water Shrine, Jake after Invincible Interior, Sakura after Magic Library – Showdown of Destiny, Blue Mage Fina at the start of Season 3, Runda in Season 4 (Trail to Yorte – Underground Nest). Each joins once per save; if you're already past that point, they join at your next login. `0` turns it off. |
| `EXVIUS_SUMMON_EXCLUSIONS` | `1` (default) keeps units Global never handed out from normal summons out of them: the story cast (Rain, Lasswell, Fina, Nichol, Lid, Sakura, Jake, Blue Mage Fina), story NPCs, and reward, Star Quartz and Raid Summon units, 78 in all, checked against the FFBE wiki. A summon that features one of them still has it. Units you already own stay. List: `ios-server/research/SUMMON_EXCLUSIONS.md`. `0` puts them back. |
| `EXVIUS_LIMITED_FEATURED_ONLY` | `1` (default) keeps limited-time, collaboration and seasonal units (Santa Roselia, the Kingdom Hearts, FFXIV, Dai and NieR units, and so on) out of regular summons: as in Global, they only come from a summon that features them. Which units count follows the FFBE wiki's mark for each unit; units the wiki lists as regular Rare Summon units, such as Gilgamesh (FFV), the summer units from 2019 on and the FFVII REMAKE units, stay in regular summons. `0` lets regular summons draw them again. |
| `EXVIUS_SELECT_LIMITED` | `1` (default) adds the limited and collaboration 5★ units Global had (80) to the 5★ Select Summon's list, at the usual 10 tickets. Story, reward and Japan-only units stay out. `0` shows the game's own list (234 regular units). |
| `EXVIUS_SELL_STORY_UNITS` | `1` (default) gives the story units above the usual sell price for their rarity, so extra copies can be sold to free up space. This also applies to the copy the story gave you, so mark it as a favourite if you want to keep it safe from selling. `0` makes them unsellable again (a phone that already has the change may keep it until the game is reinstalled). |
| `EXVIUS_COLLECTION_POINTS` | `1` (default) shows the collection points in explorations (the sparkling spots; Dalnakya Cavern has three) and gives what they gave in Global, from the FFBE wiki's lists: one item per point each run, such as ore, Lumber, a cryst or magicite, at the wiki's odds where it lists them, otherwise ores 40%, crysts 40%, magicite 20%. Event explorations give their own list or event certificates. Quests that reuse an exploration's map (the Aquapolis knight quests, character episodes) give that exploration's list. A few have no record of what their points gave and show none: Japan-only quests, Castle Exdeath, Doga's Grotto and the Water God trials. `0` hides all collection points, as before. |
| `EXVIUS_EXCHANGE_SCHEDULE` | `1` (default) has King Mog and the Mog Minister in the Vortex town run the exchange of the event that is on this week, as in Global (Mana Mystery's week: King Mog trades for Candy). Between events, each keeps the exchange of an event currency you still hold, or has nothing. The exchange shows the name of the merchant who opened it. The exchanges on the Shop's summon coin screen open while an event that pays their currency is on, or while you hold the currency; the Star Quartz unit exchanges open once the replay reaches January 2023, when Global added them. `0` brings back the old fixed shops (King Mog always Star Quartz, the Minister always Auracite Shards, every exchange always open). |
| `EXVIUS_CAPTAIN_MENU` | `1` (default) makes the Moogle Guard Captain in the Vortex town the place for leftover event currency: his menu lists every exchange whose currency you hold that King Mog and the Mog Minister aren't showing this week (events that are over, and events that lost the counter to another event in a busy week), plus his own Super Trust Moogle and Dark Visions exchanges from the dates Global added them. Events the replay hasn't reached never show. With nothing to list he says so. The exchanges he opens carry his name. The list is worked out when the game starts, so currency you get or spend shows up in his menu at the next launch (an option whose currency you spent tells you so). Each change downloads the Vortex town again (about 6.6 MB). `0` brings back the shipped menu. |
| `EXVIUS_EVENT_RUN_QUESTS` | `1` (default) has each Vortex event show only the quests it had in the run of Global's history the replay is in. Trials and stages a later run added (Chamber of the Vengeful's trials, Chamber of Arms', Twelve Types Takedown's, the later Short Stories, and so on) appear when the replay reaches the run that added them, with their currencies and exchanges. Trial chambers that started later (Chamber of the Vengeful in 2019, Chamber of Arms in 2017) appear from then. The dates come from the Brave Exvius wiki's update history. `0` shows every quest of an open event, as before. |
| `EXVIUS_HIDE_CLONE_QUESTS` | `1` (default) hides quests that are exact copies of another quest in the same event (same battle, missions and rewards), so each is listed once: Chamber of Challenges, Elemental Turn Challenge and Producer of the Crystal; also, by choice, Mana Mystery's second quest set (double mission Lapis) and Producer of the Crystal's copies with other mission rewards. List: `ios-server/research/CLONE_QUESTS.md`. `0` shows every copy again. |
| `EXVIUS_VORTEX_ORDER` | `1` (default) lists the Vortex's events in this order: story events, then the other limited-time events (newest first), then Clash of Wills and Dark Visions, then rotating events like Boss Rush, then the trial chambers (Chamber of the Fallen, of Arms, of the Vengeful), and the farming chambers at the bottom (the ones Global added last at the very bottom). The game sorts the list by a number in its area table; the server sends that table with these numbers. Open the game twice after changing it. `0` keeps the game's own order. |
| `EXVIUS_HIDDEN_EVENTS` | Vortex events kept out because they can't be played the way Global ran them, as a comma-separated list of event area ids. Default `711` (Memories from the Aquapolis, see [Known issues](#known-issues)): hidden from the Vortex, the News notices and the home banners. `0` shows them all. |
| `GACHA_RAIDS` | `1` (default) adds Global's raid summons: the Box Summons of 47 raids and the Raid Summons of 21 more, each in its raid's replay week, paid with the raid's coins. Box Summons work like Global's: the game's own box screen, up to 50 pulls at once, rewards removed from the box as you draw them, the next box once the featured rewards are drawn, then the raid's standard summon. Contents are from the FFBE wiki; odds are Global's measured ones where players recorded them, otherwise estimates (list in `ios-server/research/RAID_SUMMON_RATES.md`). `0` turns them off. |
| `EXVIUS_DEAL_ART_FETCH` | On startup, download the deal summons' banner art from the Internet Archive into `server/deal_art/` (once per image; a lost image gets a plain titled banner). Default `1`; `0` skips it, and those summons show without art. |
| `EXVIUS_WEEKLY_GIFT` | Mailed once per summon week, as `kind:id:count` items. Default `23:50:10,23:70:1`: 10 Rare Summon Tickets and a Guaranteed Ticket (4★/5★/NV), usable with any banner's Ticket Summon button. `""` turns it off. |
| `EXVIUS_FIRST_CLEAR` | `1` (default) pays each quest's first-clear reward the first time you clear it, as the original game did: Lapis (multiplied like other earned Lapis), event currency such as Mana Mystery's Candy, tickets, units, equipment and materia. The result screen lists it in its first-clear section. Quests you cleared before this setting existed don't pay when replayed; their rewards come once by mail instead (next setting). `0` turns it off. |
| `EXVIUS_FIRST_CLEAR_MISSED` | First-clear rewards of quests you cleared but were never paid for (any build), by mail at login, once per quest; a unit you already hold or a recipe you already own is left out. `1` (default) mails it; `0` turns it off; `preview` only writes what it would pay to the server log. |
| `EXVIUS_STORY_RECIPES` | `1` (default) pays the recipes the story gave on Global that the game data lost: the crafting tutorial's Bronze Knife recipe (with 3 Copper Ore, after Earth Shrine - Exit, a stand-in point) and the Magic Key recipe (first clear of Grandshelt Castle - Throne Room). Saves already past those points get them by mail once, along with any Farplane Tower of Earth gift (Murasame, Force Armor, Killer Bow, Apollo Harp) whose boss they beat without receiving it. `0` turns both off. List: `ios-server/research/STORY_RECIPES.md`. |
| `EXVIUS_GUIDE` | `1` (default) fills the Guide (Library): units (with the lower forms of awakened units), items, equipment, materia and Vision Cards you hold or have held, and monsters from battles fought from now on. `0` sends nothing (the Guide stays empty except recipes). |
| `EXVIUS_ENGLISH_SEARCH` | `1` (default) gives each Vision Card its English name as its search reading, so the Vision Card search finds cards by English name (the game's data has Japanese readings for 216 cards). `0` serves the card table as shipped. |
| `EXVIUS_FARPLANE_SCENES` | `1` (default) stops the Farplane from replaying its first scene and sending you back to Mitra on every visit: the game is told to skip two Farplane scene files that hold a copy of that first scene (the Crest scene and the end of the Moogle quests; neither survives in English). `0` sends the game's own list again (open the game twice afterwards). |
| `EXVIUS_REFETCH_TABLES` | `1` (default) makes the game download the unit conversion table (`F_SACRIFICE_MST`) again, which the Convert to Prism and Convert to Fragments lists need. `0` advertises it as shipped. |
| `EXVIUS_MISSION_GIL` | `1` (default) pays each quest's own clear Gil on every win (the Chamber of Riches pays almost all its Gil this way: 1,500 to 85,000 per run) and shows it on the result screen. `0` pays only the Gil the monsters drop. |
| `EXVIUS_EVENT_CURRENCY_RUNS` | Event currency (King Mog and similar: Mana Mystery's Candy and the rest) drops from the event's enemies, as it did on Global: Global's per-clear amounts (from the FFBE wiki, or Japan's battle data where its enemies already carry it), multiplied so the event's own gear, materia, units and tickets in its exchange take about this many clears of its top quest (never less than Global's own amount). Easier quests drop less, in Global's proportions. Default `30`; `0` gives Global's own amounts. Events where no source says which quests drop the currency still pay it once at the end of each clear instead (list in `ios-server/research/DROP_CHECK.md`). Each exchange is in the Shop's exchange list while its event is in the Vortex or while you hold its currency, with the stock it had at that event's run. |
| `EXVIUS_FIRST_CLEAR_BACKPAY` | `1` (default) sends one mail, once, with the first-clear rewards of every quest you had already cleared before first-clear rewards were paid (Lapis is multiplied when you receive it). `0` doesn't send it. |
| `EXVIUS_REPLAY_MAILS` | Global's mails to every player (the Guaranteed NV Summon Ticket in Jan 2021, the Player Appreciation tickets in Sep 2021, Feb 2022 and Jun 2022), each sent once when the replay reaches its date. Default `1`; `0` turns them off. |

**Trust from quests**

Each successful clear of any quest (story, exploration, Vortex, events) gives every unit of your own party a chance at more trust (Trust Master %); the friend's unit gains nothing. The result screen counts it up and shows the Trust Master reward when a unit reaches 100%. Each unit rolls on its own. The defaults are Japan's rule (a 30% chance of +1% per unit per clear), plus a small extra: 5% of those hits give +5% instead. That's about 280 clears for 100%. Global's rule was a 10% chance of +0.1%, about 10,000 clears. Trust Moogles, duplicates and expeditions still work as before; a Trust expedition that reaches 100% now also pays the reward.

| Setting | What it controls |
| --- | --- |
| `EXVIUS_QUEST_TRUST` | `1` (default) turns trust from quests on; `0` turns it off. |
| `EXVIUS_QUEST_TRUST_CHANCE` | Percent chance per party unit per clear. Default `30` (Japan); `10` is Global's. |
| `EXVIUS_QUEST_TRUST_POINTS` | Trust added on a hit, in tenths of a percent. Default `10` (1%, Japan); `1` (0.1%) is Global's. |
| `EXVIUS_QUEST_TRUST_BIG_CHANCE` | Percent of hits that are a big hit instead. Default `5` (so 1.5% per unit per clear); `0` turns big hits off. |
| `EXVIUS_QUEST_TRUST_BIG_POINTS` | Trust on a big hit, in tenths of a percent. Default `50` (5%). |

**Explorations**

| Setting | What it controls |
| --- | --- |
| `EXVIUS_FIELD_ENCOUNTERS` | `1` (default) gives explorations their random battles while you walk: the monsters the FFBE wiki lists for each exploration, in about the wiki's number of battles per zone, and then they run out as they did in the original game. 248 story, quest and event explorations are covered (`source/server/content/exploration_encounters.json`); the rest have no random battles. Each battle's drops are rolled from the enemies' own drop lists. `0` turns random battles off. |

**Other players**

| Setting | What it controls |
| --- | --- |
| `EXVIUS_PLAYERS` | How many made-up players exist (default `200`, gaming and anime handles). Find them under Friend > Suggestions (a new set daily) or search by id (910000001 and up). Friend requests are accepted at once, and Remove works. Each player lends a different unit every week, only from units released by the replay's point in history. `0` turns them off. |
| `EXVIUS_START_FRIENDS` | How many of them are already your friends in a new save (default `15`, enough for the "send gifts to 15 friends" daily quest). |
| `EXVIUS_PLAYER_SUGGESTIONS` | How many suggestions the Friend screen shows each day (default `10`). |
| `EXVIUS_ARENA_TOP` | The Arena's weekly leaderboard: about how many points the best of the other players reaches by the end of the week (default `12000`; 10th place ends near three quarters of it, 50th near half). The other players are the made-up accounts above, each with a five-unit team; the board resets every week (with the summon rotation) and your final rank pays that week's ranking reward. Needs `EXVIUS_PLAYERS` above 0. |
| `EXVIUS_ARENA_RIVALS` | How many Arena opponents the list shows (default `5`). The list changes every 10 minutes, from weaker (ratio 0.50) to stronger (1.50) teams; a win pays the ratio x 100 points. |

Your own hand-picked companions still come from `source/server/friends.yaml`.

**Summon rotation**

| Setting | What it controls |
| --- | --- |
| `EXVIUS_SUMMON_ROTATION` | `1` rotates banners weekly; `0` shows every banner at once. |
| `EXVIUS_ROTATION_HOLIDAYS` | `1` (default) keeps holiday summon sets (Christmas, Halloween, Valentine's Day, Easter) for the week before that holiday and the holiday's own week. Holiday events (the Christmas, Halloween, Easter and Valentine's King Mog events and the Halloween Castle; the list is `HOLIDAY_EVENTS` in `source/server/event_archive.py`) follow the same weeks and never open on their history dates. Without the replay, it's one original year at a time, oldest first, so the newest and strongest holiday units come later. `0` mixes them into the normal pool. |
| `EXVIUS_VORTEX_ROTATION` | `1` (default) makes the Vortex follow the summon rotation: the permanent dungeons are always open, plus the events that originally ran alongside this week's summon sets, so an event's featured units, coins and tickets line up with the banners you can pull. An event opens at each of its Global runs, first runs and reruns alike (`source/server/event_history.json`). Clash of Wills and Dark Visions open only during the periods Global ran them. The Vortex never shows two tiles that look the same: the Chamber of Challenges and Chamber of Crysts areas take turns a week each (Chamber of Challenges' Halloween and Christmas battles only in those holidays' weeks), and later copies of an event show only the first. Events are listed first (holiday events, then newest first), then Clash of Wills and Dark Visions, then the permanent dungeons. `0` opens all 764 archived events at once. |
| `EXVIUS_VORTEX_EXTRA` | How many undated recurring Vortex events (Boss Rush, Cactuar Dunes, Challenge of the Brave, …) open each week. Default `2`. |
| `EXVIUS_ROTATION_TZ` | Time zone of the weekly change. Default `America/New_York`. |
| `EXVIUS_ROTATION_DAY` | Day of the change. 0 is Monday, 6 is Sunday. |
| `EXVIUS_ROTATION_HOUR` | Hour of the change, in 24-hour time. |
| `EXVIUS_ROTATION_SPECIAL` | How many sets with step-up, ticket or select banners appear each week. |
| `EXVIUS_ROTATION_FEATURED` | How many other featured sets appear each week. |
| `EXVIUS_ROTATION_FIRST_WEEK` | Without the replay: release sets for the first week, by release date. Default `2016-12-16` (Noctis). Later weeks are random, and nothing repeats until the whole pool has cycled. |

**Downloads and sound**

| Setting | What it controls |
| --- | --- |
| `EXVIUS_EARLY_RESOURCES` | Resource packs downloaded up front instead of in the background. The default, `resources_common.cpk,resources.cpk`, is what the first battle needs (about 50 MB). `all` downloads everything up front in one long download; `0` turns it off. |
| `EXVIUS_IOS_DROP_UNVERSIONED` | `1` (default) leaves out of the resource list the seven entries that have no file to download (`character.cpk` and six movies). Without this the phone asks "Download while playing tutorial?" with 0 KB on every start. `0` serves the list as shipped. |
| `EXVIUS_IOS_QUEST_REWARDS` | `1` (default) lists each town quest's rewards when you take it on, instead of "???" until it's done. On the iPhone, the "???" version of the quest screen freezes or closes the game (Port City Lodin's side quests, 2026-11-07). `0` keeps the "???" (the phone keeps the patched list until the table changes again). |
| `EXVIUS_IOS_HCA_PLAIN` | `1` (default) removes the sound banks' HCA cipher, which is what makes the music play cleanly on the iPhone. |
| `EXVIUS_IOS_SOUND_REFETCH` | Set it to any new value to make the phone download every sound bank again. |
| `EXVIUS_IOS_TEXT` | `1` (default) adds the English names the stock app is missing, such as the Shop's local bundles and the special summon tickets. `0` turns it off. |
| `EXVIUS_STORY_TEXT_FIX` | `0` (default) serves the story scenes as shipped. `1` fills in the story lines three scenes are missing in the English data (chapter 1 leaving with Fina, Lid's Mechabo at Ballen Passage, and one event scene), but the iPhone can't load the rebuilt scenes yet: entering Port City Lodin gives "A loading error has occurred". Leave it at `0`. |
| `ANNIVERSARY_TICKET` | `0` (default here) stops the free 8th-Anniversary 10+1 ticket the engine otherwise mails every day. `1` turns it back on. Tickets you already received stay. |
| `EXVIUS_LAPIS_SHOP_EXCLUDE` | Products left out of the exchange shops that sell for Lapis, as `kind:id` pairs. The default, `10:900020401`, removes King Metal Minituars, which otherwise cost 3 Lapis each. Empty puts them back. |
| `EXVIUS_IOS_BANNER_FIT` | `1` (default) pads summon detail art to the shape of the frame the iPhone draws it in, so taller or wider images aren't squashed (the Android build does this with a hook). Paid summons draw it in a wide frame; the Standard (friend point) and free summons in a 640x392 one, so their art is fitted to that instead. The sides are filled with a blurred, darkened copy of the art. Needs Pillow, which the image installs. Cached in `FFBE_DIR/server/ios-cache/banner-fit/`. |
| `EXVIUS_IOS_BANNER_FIT_NAMES` | `1` (iPhone default) names each summon detail image `<name>-fit1.png` (`<name>-full1.png` for the Standard and free summons) in the summon tables. The phone keeps every banner image it has downloaded and never asks again, so without a new name it keeps the squashed copy. The server maps the name back to the real file. |
| `EXVIUS_BANNER_DEALS` | `1` (default) pays the extras printed on summon banner art that the banner data left out: free Trust Moogles with every 10+1, bonus coins and tickets, and from October 2020 a guaranteed 5★/NV unit plus a Summon Coin with every 11 summon. 107 banners, listed in `source/server/banner_deals.json`. `0` turns it off. |
| `EXVIUS_IOS_VORTEX_ART` | `1` (default) builds the Vortex banner pack the iPhone needs, so event tiles show their art (and the Enhance tab doesn't crash). It's built when the server starts and cached in `FFBE_DIR/server/ios-cache/` (about 240 MB). |

If you have original **iOS** sound banks, put them in `FFBE_DIR/data/native/common_lang/sound/<bgm or se>/ios/`, keeping their `Ver<N>_` file names. The server sends those as they are, ahead of the Android ones.

---

## How it was made to work

The preserved game data comes from the Android version, and the iPhone app was never meant to talk to anything but the real servers. These are the problems that came up, and what the server does about each. The details are in the code comments in [`source/server/`](source/server/).

1. **Reaching the server.** The app has its server addresses built in, so the server has to be found under those names. A DNS responder answers only the game's domains, and Tailscale split DNS sends only those questions to it. The app accepts the private certificate once it's trusted in **Certificate Trust Settings**. Installing the profile alone isn't enough.
2. **Data tables failing to load (`MST_LOAD_FAILURE`).** The stock app ships with data tables of its own, and mixing them with the server's fails. The server advertises every table at its real version plus 200000 (`EXVIUS_TABLE_VERSION_OFFSET`), so the app replaces all of its own. Then the iPhone's decoder rejected tables that had been rebuilt with Windows (CRLF) line endings, which Android tolerates; the server converts them to LF as it sends them.
3. **Missing sound files.** The app asks for `…/sound/…/ios/…`, but the preserved data only has `…/android/…`. The bank format is the same on both, so the server answers iOS sound requests from the Android folder.
4. **Crash entering the first battle.** The opening battle loads two layout files from two resource packs that the game normally leaves near the end of its background download, so the battle started before they arrived. The server marks those packs for the up-front download (`ios_tables.py`). The phone only gets the changed list at login, which is why the second launch matters.
5. **Garbled music and sound effects.** Every Android sound bank uses CRI HCA cipher type 1, a fixed keyless scrambling table. The iPhone played the banks as loud noise, the same noise a decoder makes when it skips that table. The server removes the cipher as it sends each bank (`sound_compat.py`): it decrypts every audio frame, marks the file unencrypted and rewrites the checksums. The audio and the file size stay exactly the same. Because the phone never re-downloads a file it already has, the server also gives every sound file a new version number whenever these settings change.
6. **Names showing as codes.** The Android build fills in some names itself, with code hooks inside the app (for example the Shop's local bundles, `MST_BUNDLE_NAME_990000108`). The stock iPhone app has no hooks, so it showed the raw keys. The server adds those names to the game's own text tables instead, and gives the changed tables new versions so the phone downloads them (`ios_texts.py`). The same goes for everything else the Android hooks fill in (reconstructed abilities, monster names, event mode names) and for obtainable items that never had English text, such as the SP Summon Tickets' descriptions (`ios_text_items.json`).
7. **Blank Vortex tiles, and a crash on the Enhance tab.** Each Vortex tile's picture is loaded by name from the game's mounted data packs, and the archive's event banners only existed as loose PNG files, which the Android version hands to the game with in-app code. The server now rebuilds the game's own Vortex banner pack with those pictures added, gives it a new version, and puts it in the up-front download (`ios_art.py`).
8. **Seeing what the phone is doing.** iOS hides apps' logs, so the server can turn on the game's own crash-report upload and save what it sends (`client_reports.py`, `EXVIUS_CLIENT_REPORTS=1`; off by default since 2026-11-10, and when on it asks once per launch). Every step above was diagnosed from those reports.

The weekly summon rotation is in `source/server/gacha_rotation.py`, the historical replay in `source/server/replay.py` (unit release dates in `unit_release.json`), and the News board notices in `source/server/replay_notices.py`. The notice rows use the layout the app's own notice reader expects, read from the Android build of the game.

---

## Removing everything

1. On the computer running the server, from `exvius/repo/ios-server`:

   ```bash
   docker compose down --rmi local
   ```

   Then, unless something else on this computer uses the official Tailscale image:

   ```bash
   docker image rm tailscale/tailscale:stable
   ```

   On Unraid with the template: remove `ffbe` in the Docker tab (icon → **Remove**), run `docker image rm ffbe-ios-server:local`, and delete `/boot/config/plugins/dockerMan/templates-user/my-ffbe.xml`.

   Then delete the whole `exvius` folder (or your `FFBE_DIR`). That removes the game data (including the event banners the server downloads from the Brave Exvius wiki into `data/native/en/sd/area/`, and the deal summons' art it downloads into `server/deal_art/`), your save, the certificates, the Tailscale state and this copy of the repo.
2. In the Tailscale admin console:
   - **Machines → ffbe → ⋯ → Remove.**
   - **DNS:** delete the nameserver entries for `gumi.sg` and `exvius.com`.
   - **Settings → Keys:** revoke the auth key if it's still listed.
3. On the iPhone: **Settings → General → VPN & Device Management → Exvius Offline server → Remove Profile.** This also removes the trusted certificate.

Nothing else on your computer, network or tailnet is changed.

## Credits

The game engine, the preserved game data and the original Android app are [Exvius Offline](https://github.com/Elvlin/exvius-offline) by Elvlin. This project adds the iPhone server around it. The game data is downloaded from that project's GitHub releases during setup.

Final Fantasy Brave Exvius belongs to Square Enix and gumi. This is an unofficial fan project, not affiliated with either.
