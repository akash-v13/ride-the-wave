# Moving Ride The Wave to a Mac mini

The Mac mini becomes the always-on home for the bot, the database, the web page and the research. The
laptop goes back to being a laptop. Chosen on 2026-10-28 over a $24-a-month cloud server, after a month in which the
laptop slept through most trading sessions (`docs/progress.md`, 2026-10-28).

The scheduled jobs and the `caffeinate` sleep blocker are already macOS-native. Two operator features were
added for the move on 2026-10-28: a watchdog that starts the bot again after a restart in trading hours, and
alerts pushed to your phone (section 7). Otherwise the work is setting the machine up so it never sleeps and restarts on its own, and
handing over from the laptop cleanly.

**The one rule: never let two machines run the bot.** Both would trade the same paper account, each with
its own database, and each would treat the other's orders as unknown. Step 4 switches the laptop off
before the Mac mini switches on. Do the move after the close, ideally on a Friday evening or a weekend.

That includes test runs. Even `run_bot.py --dry-run` takes over every live position it finds in the paper
account, and its exit rules can sell them. So any run on the Mac mini, test or real, happens only after
the close, when the laptop's bot has stopped and Wave Rider has flattened. If the handover goes wrong,
there is a way back: run `uv run python scripts/install_launchd.py install` on the laptop before the next
open. Its copy is untouched as long as the Mac mini has not traded a session. After that, the Mac mini's
database is the real one.

## Done on 2026-10-28: how it was actually set up

The move happened the evening of 28 October, after the close. Most of it was done over SSH from the
laptop. Where it differs from the steps below:

| Item | As set up | Why |
|---|---|---|
| Machine | The Mac mini, user `admin`, macOS 27.0.1, Central time | |
| Project folder | `/Users/admin/Projects/Finance/Ride The Wave` | Not under Desktop: macOS privacy protection covers Desktop, Documents and Downloads, and can block a scheduled job from reading them without showing any prompt |
| Python | uv 0.13.6 in `~/.local/bin`, installed with uv's own installer | No administrator password needed, so it could be done over SSH |
| Node | 26.9.0 from nodejs.org, checksum verified, in `~/.local/node`, linked from `~/.local/bin` | Same reason. Homebrew is not installed; nothing needs it. Add it later for `poppler` |
| GitHub CLI | `gh` 2.103.3 from GitHub's release page, checksum and Apple notarization checked, in `~/.local/bin`. Signed in on 2026-10-29 with GitHub's device login; the token is in the macOS keychain, and `git` uses it through `gh auth setup-git` | Pull requests are opened from the Mac mini now that the laptop's copy is archived. The login can reach every repository on the account, and the Mac mini logs in by itself, so revoke it at github.com/settings/applications if the machine ever leaves home |
| Energy, FileVault, login | Already right: sleep off, wake on network, restart after a power failure, FileVault off, automatic login as `admin` | |
| Claude Code memory | Copied and renamed to `~/.claude/projects/-Users-admin-Projects-Finance-Ride-The-Wave` | The folder name follows the project path |
| Laptop | Scheduled jobs removed; `.env` renamed to `.env.disabled-moved-to-mac-mini` | Never two bots on one account |
| Remote access | Tailscale on both, key expiry off for the Mac mini. Its Tailscale name and address are in the Tailscale admin console, not here, because the repository is public. The laptop's `~/.ssh/config` has `ssh mini` for a terminal and `ssh -N mini-web` to open the web page at http://localhost:8787. VS Code Remote-SSH can use host `mini`. Screen Sharing is on and was reached from the laptop over Tailscale on 2026-10-29: `open vnc://<mini-tailscale-name>`, then sign in as `admin` with the Mac mini's login password | Works at home and away, with no router ports opened |
| Checks on the Mac mini | `check_env.py` all passed, 136 Python and 3 web tests, dry run with a 61-stock universe, test push delivered | |

When the scheduled jobs were installed, launchd started the bot at once, because its job is kept alive.
It waits for the next open. The 05:30 run does not start a second copy while one is running.

The laptop's project folder is now a stale copy. Work on the Mac mini's copy, over SSH or VS Code
Remote-SSH: `admin@<mini-name>.local` at home, or `admin@<mini-tailscale-name>` away from home.

## The machine: Mac mini M1 (2020), 8 GB memory, 256 GB disk

It is enough, with room to spare. Measured on 2026-10-28:

| What | Memory at peak |
|---|---|
| macOS and background services | about 3 GB |
| The bot during a session | about 0.2 to 0.4 GB (215 MB at start-up) |
| Web API and Streamlit dashboard | about 0.3 GB |
| Claude Code and VS Code's remote server, while you work on it | about 1 GB |
| The largest research job: the ten-year survivorship-free panel | 2.4 GB |

That is about 7 GB with everything running at once, so the heavy studies are best run outside market
hours. macOS swaps to disk if it runs short, which would slow the bot's 15-second ticks rather than break
them.

Disk: the project is about 2.6 GB, including 2 GB of data and the Python environment. The database grows
by about 25,000 minute bars a trading day, roughly 1 GB a year. macOS takes 30 to 40 GB of the 256, so
space lasts for years.

macOS: Homebrew now requires macOS 15 Sequoia or later. Before anything else, run Software Update and
install the newest macOS it offers.

There is no battery, so any power blip restarts it (see step 2.7).

## 1. Until the Mac mini is set up

Keep the laptop plugged in with the lid open in market hours, and set the wake schedule once:

```bash
sudo pmset repeat wakeorpoweron MTWRF 08:05:00
```

## 2. Set up macOS on the Mac mini

1. **Same username and folder as the laptop** (`<laptop-user>`, project under
   `~/Desktop/Projects/Finance/Ride The Wave`). The bot does not need this, since every path is worked out
   at install time. Claude Code does: it files its project memory under a folder named after the project's
   full path, so the same path means the memory carries over as is.
2. **Ethernet, not Wi-Fi.** One less thing to drop.
3. **Energy** (System Settings, Energy), or the same in one command:
   - Prevent automatic sleeping when the display is off: on. The display may sleep; the computer must not.
   - Wake for network access: on.
   - Start up automatically after a power failure: on.

   ```bash
   sudo pmset -a sleep 0 disksleep 0 womp 1 autorestart 1
   pmset -g        # check: sleep 0, autorestart 1
   ```
4. **Log in by itself after a restart: a choice to make.** The scheduled jobs are user agents, so they only
   start once a user is logged in. If this is a Mac mini you already use, that account works. If its
   username differs from the laptop's, only Claude Code's memory folder needs renaming (section 4.3). After a power cut the Mac restarts by itself, then waits at the login
   screen.
   - FileVault off and automatic login on (System Settings, Users and Groups): the Mac comes back fully
     unattended. The cost is that anyone who can physically reach it can use it. The keys in `.env` are
     paper-trading keys plus the Jev key.
   - FileVault on: the disk stays encrypted, and after a power cut nothing runs until you type the password.
     A sleeping bot raises no alert, so you would find out at the next check-in.

   Recommended if the Mac mini is dedicated to this and stays at home: FileVault off, automatic login on.
5. **macOS updates: not on their own during market hours.** System Settings, General, Software Update,
   Automatic Updates: keep "Install Security Responses and system files" on, and turn "Install macOS
   updates" off. Install those by hand at a weekend. An automatic update restarts the Mac whenever it likes.
6. **Remote access.** System Settings, General, Sharing: turn on Remote Login (SSH) and Screen Sharing.
   At home, `ssh <user>@<mini-name>.local` works from the laptop. To reach it from anywhere,
   set up Tailscale (section 8). Do not open ports on the router: the web page can pause and flatten
   strategies, and it has no login of its own.
7. **A small UPS** (battery backup) is worth it here, because the Mac mini has no battery. Without one,
   any blip restarts it. A restart in market hours is covered. launchd starts the bot again as soon as
   the Mac logs in, because the bot's keep-alive setting implies start at load; the restart test on
   2026-10-28 showed this. The operator tick's watchdog is a backup that would start it within about
   five minutes and send a phone alert. Since 2026-10-29 it also starts the bot if the 06:30 ET morning
   start did not run (`docs/features/14-operator.md`, section 4). Both need automatic login (item 4),
   which is on (checked 2026-10-29: auto-login `admin`, FileVault off). A UPS still saves the minutes
   lost and any half-finished tick.

## 3. Install the tools on the Mac mini

```bash
xcode-select --install                                   # git and compilers
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install uv node gh poppler
node --version                                           # needs 26 or later (the laptop has 26.9)
```

Python 3.12 does not need a separate install: `uv sync` in step 5 fetches the version `pyproject.toml`
asks for. Background on each tool: `docs/requirements.md`.

## 4. Hand over from the laptop (after the close)

1. **Stop everything on the laptop.** This is the moment the laptop stops trading.

   ```bash
   cd ~/Desktop/Projects/Finance/"Ride The Wave"
   uv run python scripts/install_launchd.py remove
   uv run python scripts/install_launchd.py status       # nothing listed
   pgrep -fl "run_bot|server.js|run_ui" || echo "nothing running"
   ```
2. **Pack the whole project folder**, without the two folders each machine builds for itself (the Python
   environment and the Node packages, about 600 MB):

   ```bash
   cd ~/Desktop/Projects/Finance
   tar --exclude "Ride The Wave/.venv" --exclude "Ride The Wave/web/node_modules" -czf ~/Desktop/rtw.tgz "Ride The Wave"
   ```

   The whole folder, not a `git clone`, because git does not carry the database (`data/`, 2 GB), the keys
   (`.env`), the settings in use (`config/settings.yaml`), the book PDFs, or any work not yet committed. The
   database is copied while nothing writes to it, which is why step 1 comes first.
3. **Pack Claude Code's memory and your knowledge base**, if Claude Code will run on the Mac mini:

   ```bash
   cd ~
   tar -czf ~/Desktop/claude-context.tgz .claude/projects/-Users-<laptop-user>-Desktop-Projects-Finance-Ride-The-Wave .claude/CLAUDE.md brain
   ```

   Claude Code names that memory folder after the project's full path. If the Mac mini's username is not
   the laptop's, rename the folder after unpacking, putting the Mac mini's username in place of
   the laptop's. The same goes for any other difference in the path.
4. Move both files to the Mac mini by AirDrop, a USB drive or Finder file sharing. They contain the API keys,
   so do not use a cloud drive or email.
5. **Unpack on the Mac mini:**

   ```bash
   mkdir -p ~/Desktop/Projects/Finance
   tar -xzf ~/Downloads/rtw.tgz -C ~/Desktop/Projects/Finance
   tar -xzf ~/Downloads/claude-context.tgz -C ~
   ```

## 5. Build, check and switch on (Mac mini)

```bash
cd ~/Desktop/Projects/Finance/"Ride The Wave"
uv sync --all-groups                                     # Python 3.12 + packages, incl. dev and jev groups
(cd web && npm ci && npm run build)                      # the TypeScript API and web page
uv run python scripts/check_env.py                       # keys, paper endpoint, data plan, database
uv run pytest -q                                         # 136 tests
uv run python scripts/run_bot.py --dry-run               # builds the universe and every slot, trades nothing
uv run python scripts/install_launchd.py install         # bot, operator tick, API
uv run python scripts/install_launchd.py status
curl -s localhost:8787/api/health
uv run python scripts/notify_test.py                     # phone alerts; set up NTFY_TOPIC first (section 7)
```

The dry run should end with `dry run complete` and a universe of about 60 stocks.

## 6. The first trading day on the Mac mini

- 09:00 ET pre-market report: the bot is waiting for the open, and the universe has stocks.
- After the close, look for gaps in the log. Ticks every 15 seconds mean a full session runs about 1,500
  ticks with no gap over a minute or two.

  ```bash
  grep -c "_tick:" data/logs/bot-$(date +%Y%m%d).log      # one line every 20 ticks: about 75 for a full day
  grep -E "ERROR|universe build failed" data/logs/bot-$(date +%Y%m%d).log | head
  ```
- Ask Claude for a status check: it compares the session against the October failure modes.

## 7. Afterwards

- **On the laptop, disable the keys** so a stray manual run cannot trade the same account:
  `mv .env .env.disabled-moved-to-mac-mini`. Keep the folder for reading if you like, and never run
  `install_launchd.py install` there again.
- **Working on the project from the laptop:** VS Code's Remote-SSH extension opens the Mac mini's folder,
  and Claude Code runs inside it on the Mac mini, next to the data. Or use Screen Sharing.
- **Alerts on your phone (ntfy).** macOS notifications pop up on the Mac mini's screen, where nobody sees
  them, so every alert is also pushed to your phone through ntfy (https://ntfy.sh, free, no account). Set
  it up before the first session you will not be at home for:
  1. Install the ntfy app on the phone.
  2. Make up a long random topic name: `python3 -c "import secrets; print('rtw-' + secrets.token_urlsafe(16))"`.
     Anyone who knows the name can read the alerts, so treat it like a password.
  3. In the app, subscribe to that topic on ntfy.sh.
  4. Add `NTFY_TOPIC=<the name>` to `.env` on the Mac mini.

  Done on 2026-10-28: a topic was created and put in the laptop's `.env`, which travels with the project,
  so steps 2 and 4 are already done. Only subscribe in the app. The name is in `.env`, never in these docs,
  because the repository is public.
  5. Run `uv run python scripts/notify_test.py`. It should print `delivered` and the phone should show
     "Ride The Wave: test alert from <the Mac's name>".

  Details, priorities and how to switch it off: `docs/features/14-operator.md`, section 5.
- **Docs to update once it runs:** CLAUDE.md (status and machine), the handbook's chapter 7 "What must be
  true of the machine", in both the shared doc and `docs/handbook.md`.

## 8. Reaching the Mac mini from anywhere

Tailscale puts the Mac mini, the laptop and your phone on a private network of their own, wherever each
one is. Nothing on the home router is opened, and nobody outside your account can see the Mac mini. The
personal plan is free.

1. Install Tailscale on the Mac mini and the laptop, from tailscale.com or the Mac App Store. Sign in to
   the same account on both. Add the phone too if you want to check in from it.
2. **Turn off key expiry for the Mac mini.** By default each device must sign in again every 180 days.
   When the key expires, connections to it stop, and nobody will be at the Mac mini to sign in. In the
   Tailscale admin console: Machines, the Mac mini's row, the menu at the far right, Disable Key Expiry.
3. Set Tailscale to open at login on the Mac mini (its menu-bar settings), so it comes back after a restart.

Then, from anywhere, use the Mac mini's Tailscale name, shown in the admin console:

| To | Do |
|---|---|
| Get a terminal | `ssh admin@<mini-tailscale-name>` |
| See its screen | Screen Sharing app, connect to `<mini-tailscale-name>` |
| Work in VS Code with Claude Code | Remote-SSH extension, host `admin@<mini-tailscale-name>` |
| Open the web page and dashboard | Start a tunnel, then open http://localhost:8787 (web page) and http://localhost:8501 (Streamlit) on the laptop |

```bash
ssh -N -L 8787:localhost:8787 -L 8501:localhost:8501 admin@<mini-tailscale-name>
```

**Screen Sharing: lock the screen or close the window, never log out.** The bot, the operator tick and
the web API are launchd jobs that run inside the `admin` login session. Locking the screen or closing
the Screen Sharing window leaves them running. Logging out stops all three until the next login. A
restart is safe, because automatic login brings them back. A Claude Code session started on the Mac
mini's screen also keeps running after you close the window.

The web page and dashboard listen only on the Mac mini itself, and that stays so. The tunnel carries
them to the laptop inside the SSH connection, so only someone who can log in to the Mac mini can use
them. Reaching them from the phone's browser needs `tailscale serve` on the Mac mini, which shares a port
with your own devices only. That is not set up yet.

If remote access ever fails, check the Tailscale admin console first: the Mac mini shows as offline if it
lost power, lost its network or is stuck at a login screen.

