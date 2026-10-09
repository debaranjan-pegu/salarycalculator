# Salary Calculator

An offline salary-breakup calculator with a minimum-wage engine, editable
masters, user accounts and a formatted Excel export. It replaces a spreadsheet
with a proper database and a live web UI.

- **Nothing to install by hand** — if the machine has no Python 3, the setup
  scripts install it for you; the Windows portable bundle even ships its own.
- **Runs on Windows, macOS and Linux.** No packages, no build step.
- **Works without internet.** All your data stays in one `salary.db` file.
- **Share with your team** over your local network, or use it on your own PC.

## Quick start

**Windows, no Python and no internet — the portable bundle.** Download
`SalaryCalculator-Windows-x64.zip` from the
[Releases page](https://github.com/debaranjan-pegu/salarycalculator/releases),
unzip it anywhere and double-click **`Salary Calculator.cmd`**. It carries its
own copy of Python, so there is nothing to install at all.

**Windows, ordinary route:** download the ZIP, unzip, double-click **`run.bat`**
— if Python is missing it is downloaded and installed silently first.

**macOS / Linux — one line:**

```bash
curl -fsSL https://raw.githubusercontent.com/debaranjan-pegu/salarycalculator/main/bootstrap.sh | bash
```

Or clone it yourself:

```bash
git clone https://github.com/debaranjan-pegu/salarycalculator.git
cd salarycalculator
./run.sh          # macOS: double-click run.command
```

Your browser opens at <http://127.0.0.1:8765/>. If Python 3 is missing, the
script offers to install it (Homebrew or the Apple command-line tools on macOS;
`apt` / `dnf` / `pacman` / `zypper` on Linux) and tells you exactly what to do if
it cannot.

## The things you can run

| I want to… | macOS | Windows | Linux |
| --- | --- | --- | --- |
| **use it myself** | `run.command` | `run.bat` | `./run.sh` |
| **share with my team** | `share.command` | `share.bat` | `./share.sh` |
| **start automatically, like Excel** | `install.command` | `install.bat` | `./install.sh` |
| **stop starting automatically** | `uninstall.command` | `uninstall.bat` | `./uninstall.sh` |
| **upgrade to the latest version** | `upgrade.command` | `upgrade.bat` | `./upgrade.sh` |

Every one of these is a thin wrapper around `setup.sh` / `setup.bat`, so you can
also just run `./setup.sh run|share|install|uninstall|upgrade`.

### Sharing with your team

Run `share.command` / `share.bat` / `share.sh` **on the one computer that will
host it**. It prints an address like:

```
  Share with your team:
     https://192.168.1.24:8765/
```

Give that address to your colleagues — **they install nothing**, they just open
it in a browser.

**Access is by account, not by link.** You (the administrator) create a user for
each colleague under **Users & Access** and give them their username and the
one-time password. They change it at first sign-in. Sharing the link alone does
not let anyone in — which is what you want for salary data.

The host serves **HTTPS** with a certificate it generates for itself on first
use (`certs/`). Each person sees a one-time “certificate not trusted” warning;
that is expected. To silence it permanently:

- **macOS:** open `certs/salarycalc-cert.pem` in *Keychain Access* → *System* →
  **Always Trust**.
- **Windows:** double-click `certs/salarycalc-cert.pem` → *Install Certificate*
  → *Local Machine* → *Trusted Root Certification Authorities*.
- **Linux:** copy it to `/usr/local/share/ca-certificates/`, then
  `sudo update-ca-certificates`.

Keep the host awake while the team uses it, and allow the incoming-connection
prompt the first time. Everyone should be on the same network (or your VPN).

### Starting automatically

`install.command` / `install.bat` / `install.sh` register the app to start when
you log in — a **LaunchAgent** on macOS, a **Startup shortcut** on Windows (no
console window), a **systemd --user service** on Linux. Each asks whether to run
in share mode. Afterwards, double-clicking `run.command` simply opens the app if
it is already running instead of starting a second copy.

## Upgrading

When a new version is released:

- **macOS / Windows:** double-click `upgrade.command` / `upgrade.bat`.
- **Linux:** `./upgrade.sh`

That pulls the latest code from GitHub and restarts the app if it is running.
**Your data is never touched** — everything lives in `salary.db`, which is not
part of the code. (The portable Windows bundle cannot self-update; download the
new bundle and copy your `salary.db` across.)

You can also check from inside the app: **avatar menu → ℹ️ About → 🔄 Check for
updates**.

## First run

Create the **administrator account**, then save the **one-time recovery code**
it shows you.

| Role | Can do |
| --- | --- |
| **Administrator** | everything, plus Users & Access, statutory rules, masters import/export and reset |
| **User** | calculator, records, masters, Excel export |

**Lost the admin password?** Use *Forgot your password?* with the recovery code,
or run `python3 app.py --reset-admin` on the host machine.

## Features

- **Calculator** — candidate, company, location, CTC and increment → live
  monthly/annual breakup, take-home, cost composition and minimum-wage
  warnings. Every dropdown is searchable.
- **Forwards or backwards** — set the *Proposed CTC* directly and the implied
  increment is shown live, or enter a **target monthly take-home** and let the
  app solve for the CTC that pays it. When the minimum wage makes the CTC
  impossible, one click raises it to the figure required.
- **Minimum-wage rule** — the Basic is floored at the statutory minimum; HRA and
  the General Purpose Allowance are adjusted so the CTC stays the same. If the
  floor cannot be met at that CTC, the app says so and shows the CTC required.
- **Saved Records** — save (it asks for the candidate name and records who saved
  it and when), reopen with ✏️ to edit and re-save, duplicate, delete.
- **Masters** — Countries, Companies, States, Cities, Wage categories and
  Minimum wages, with search, pagination and **⬇️ Export / ⬆️ Import** for
  backup or pushing an updated wage list to other machines.
- **Bulk minimum wages** — on the *Minimum wages* tab, **⬇️ Wage template**
  gives you a CSV listing every city (with today's figures pre-filled);
  fill the `amount` column and use **⬆️ Import wages**. You get a preview
  first: rows read, what will change, and every problem with its line number.
  Nothing is written until you press Apply, and the app never invents a figure.
- **Data health** — errors, warnings and every city still missing a wage.
- **Excel export** — a formatted `.xlsx` with a *Current CTC* column beside
  *Proposed CTC*, matching the original workbook.
- **Themes** — System / Light / Dark, and a collapsible menu.

## Requirements

Python **3.9+** — installed automatically if missing, or use the Windows
portable bundle which includes it. No packages, no build step, no database
server.

## Security

- Binds to `127.0.0.1` unless you choose share mode.
- Passwords: **PBKDF2-HMAC-SHA256**, 240,000 iterations, per-user salt.
- Sessions: random 256-bit token, HttpOnly + SameSite=Strict cookie, only a
  SHA-256 digest stored; `Secure` flag over HTTPS.
- Sign-in is rate-limited per address and locked per account; cross-origin
  state-changing requests are refused; TLS 1.2+ in share mode.
- Built for a **trusted local network**. To expose it to the internet, put it
  behind a VPN or a reverse proxy.

## Files

```
app.py          server, JSON API, auth, HTTPS, update check
auth.py         password hashing, sessions, recovery codes
certgen.py      self-signed certificate generator (no dependencies)
calc.py         calculation engine (pure functions)
db.py           SQLite schema, CRUD, users, sessions, validation
xlsx.py         dependency-free .xlsx writer
report.py       the formatted Excel report layout
seed/           the India master data
static/         index.html · styles.css · app.js
setup.sh/.bat   the real setup logic (Python install, auto-start)
run.* share.*   thin wrappers for each mode
install.* uninstall.* upgrade.*   start-up and update helpers
bootstrap.sh    one-line installer (macOS / Linux)
build_windows_bundle.sh   builds dist/SalaryCalculator-Windows-x64.zip
VERSION         the released version
salary.db       created on first run — all your data (never committed)
```

## Contributing

Issues and pull requests are welcome. Plain Python and vanilla JavaScript, no
build step — edit and refresh.

## License

[MIT](LICENSE) © 2026 Debaranjan Pegu
