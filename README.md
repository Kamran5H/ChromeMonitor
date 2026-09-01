# ChromeMonitor

> **Owner:** Kamran Ashraf. A small Windows background utility (Python) that monitors Chrome — profiles, extensions, and activity — and logs what it sees.

## What it does

`chrome_monitor.py` watches Chrome profiles/extensions and writes an automation log. It can be installed to run at Windows startup via `.vbs`/`.bat` helpers, and uses a lock file so only one instance runs.

## Files

| File | Role |
|------|------|
| `chrome_monitor.py` | The monitor script |
| `active_profiles.json` | Snapshot of active Chrome profiles it tracks |
| `extension_snapshot.json` | Snapshot of installed extensions |
| `install_startup.bat` | Registers the monitor to launch at Windows startup |
| `start_monitor.vbs` / `stop_monitor.bat` | Start (silently) / stop the monitor |

## How to run

```bat
python chrome_monitor.py
```

Or install it to start with Windows: run `install_startup.bat` once.

> Runtime artifacts (`*.log`, `*.lock`, `__pycache__/`) are excluded from git.
