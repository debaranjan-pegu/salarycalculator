# Salary Calculator

An offline salary-breakup calculator with a minimum-wage engine, editable
masters, user accounts and a formatted Excel export. It replaces a spreadsheet
with a proper database and a live web UI.

- **No dependencies** — Python 3 standard library only. No `pip install`.
- **Runs on Windows, macOS and Linux.**
- **Works without internet.** All data stays in one `salary.db` file.
- **Share with your team** over your local network, or just use it on your own PC.

## Quick start

**macOS / Linux — one line:**

```bash
curl -fsSL https://raw.githubusercontent.com/debaranjan-pegu/salarycalculator/main/bootstrap.sh | bash
```

**Windows:** download the ZIP, unzip, double-click **`run.bat`**.

Or clone it yourself:

```bash
git clone https://github.com/debaranjan-pegu/salarycalculator.git
cd salarycalculator
python3 app.py
```

Your browser opens at <http://127.0.0.1:8765/>.

> Windows: install [Python 3](https://www.python.org/downloads/) and tick
> **“Add python.exe to PATH”**. That is the only prerequisite.

## Two ways to run it

| I want to… | macOS | Windows | Linux |
| --- | --- | --- | --- |
| **use it myself** | `run.command` | `run.bat` | `./run.sh` |
| **share with my team** | `share.command` | `share.bat` | `./share.sh` |
| **start automatically, like Excel** | `install.command` | `install.bat` | `./install.sh` |
| **turn auto-start off** | `uninstall.command` | `uninstall.bat` | `./uninstall.sh` |

### Sharing with the team

Run `share.command` / `share.bat` / `share.sh` **on the one computer that will
host it**. It prints an address like:

```
  Share with your team:
     https://192.168.1.24:8765/
```

Give that address to your colleagues — **they install nothing**, they just open
it in a browser.

**Access is by account, not by link.** You (the administrator) create a user for
each colleague under **Users & Access**, and give them their username and the
one-time password. They change it at first sign-in. So sharing the link alone
does not let anyone in — which is what you want for salary data.

The host serves **HTTPS** with a certificate it generates for itself on first
use (`app/certs/`). Each person sees a one-time “certificate not trusted”
warning; that is expected. To silence it permanently:

- **macOS:** open `certs/salarycalc-cert.pem` in *Keychain Access* → *System* →
  set to **Always Trust**.
- **Windows:** double-click `certs/salarycalc-cert.pem` → *Install Certificate*
  → *Local Machine* → *Trusted Root Certification Authorities*.
- **Linux:** copy it to `/usr/local/share/ca-certificates/` and run
  `sudo update-ca-certificates`.

Keep the host awake while the team uses it, and allow the incoming-connection
prompt the first time. Everyone should be on the same network (or your VPN).

### Starting automatically

`install.command` / `install.bat` / `install.sh` register the app to start when
you log in — the macOS one as a **LaunchAgent**, Windows as a **Startup
shortcut** (hidden, no console window), Linux as a **systemd --user service**.
Each asks whether to run in share mode. Double-clicking `run.command` later
simply opens the app if it is already running, instead of starting a second copy.

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
- **Minimum-wage rule** — the Basic is floored at the statutory minimum; HRA and
  the General Purpose Allowance are adjusted so the CTC stays the same. If the
  floor cannot be met at that CTC, the app says so and shows the CTC required.
- **Saved Records** — save (it asks for the candidate name and records who saved
  it and when), reopen with ✏️ to edit and re-save, duplicate, delete.
- **Masters** — Countries, Companies, States, Cities, Wage categories and
  Minimum wages, with search, pagination and **⬇️ Export / ⬆️ Import** for
  backup or pushing an updated wage list to other machines.
- **Data health** — errors, warnings and every city still missing a wage.
- **Excel export** — a formatted `.xlsx` with a *Current CTC* column beside
  *Proposed CTC*, matching the original workbook.
- **Themes** — System / Light / Dark, and a collapsible menu.

## Requirements

Python **3.9+**. Nothing else — no packages, no build step, no database server.

## Security

- Binds to `127.0.0.1` unless you choose share mode.
- Passwords: **PBKDF2-HMAC-SHA256**, 240,000 iterations, per-user salt.
- Sessions: random 256-bit token, HttpOnly + SameSite=Strict cookie, only a
  SHA-256 digest stored; `Secure` flag over HTTPS.
- Sign-in is rate-limited per address and locked per account; cross-origin
  state-changing requests are refused; TLS 1.2+ in share mode.
- Authored for a **trusted local network**. To expose it to the internet, put it
  behind a VPN or a proper reverse proxy.

## Files

```
app.py          server, JSON API, auth, HTTPS
auth.py         password hashing, sessions, recovery codes
certgen.py      self-signed certificate generator (no dependencies)
calc.py         calculation engine (pure functions)
db.py           SQLite schema, CRUD, users, sessions, validation
xlsx.py         dependency-free .xlsx writer
report.py       the formatted Excel report layout
seed/           the India master data
static/         index.html · styles.css · app.js
run.*           run for yourself
share.*         run for the team
install.*       start automatically at login
uninstall.*     stop starting automatically
bootstrap.sh    one-line installer (macOS / Linux)
salary.db       created on first run — all your data
```

## Contributing

Issues and pull requests are welcome. The whole app is plain Python and vanilla
JavaScript with no build step, so you can edit and refresh.

## License

[MIT](LICENSE) © 2026 Debaranjan Pegu
