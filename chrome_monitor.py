import os
import sys
import time
import json
import math
import subprocess
import msvcrt

# ----------------------------------------------------------------------------
# Chrome Auto-Restart Monitor
#
# On a Chrome crash/close it performs FOUR steps, strictly in order:
#   1. Re-open every profile window that was active (reloading any unpacked
#      dev extension that got removed/disabled by passing --load-extension).
#   2. Wait for the windows to actually appear.
#   3. Arrange the windows in a tidy grid on the primary monitor.
#   4. Click the configured toolbar extension(s) (Source Genius) in each
#      window so the side panel / service worker wakes up.
#
# Every step is logged and verified before the next runs.
# ----------------------------------------------------------------------------

# Settings
CHECK_INTERVAL = 10        # seconds between status checks
ACTIVE_THRESHOLD = 300     # seconds — profile file mtime recency to count as active
LAUNCH_DELAY = 4           # seconds between launching each profile
RESTORE_COOLDOWN = 90      # seconds before another restore attempt is allowed
LOG_MAX_BYTES = 1_000_000  # rotate log at 1 MB
WINDOW_WAIT_TIMEOUT = 40   # seconds to wait for Chrome windows to appear
WINDOW_SETTLE = 6          # seconds after windows appear before arranging/clicking

# Names of the toolbar extensions to click after launch (substring match on the
# button's accessible name). These are Kamran's own dev extensions that need a
# click to wake up after a restart.
CLICK_EXTENSIONS = ["Source Genius", "Auto Clear"]

# Profile directories that are internal to Chrome and must never be treated as
# real user profiles.
IGNORED_PROFILES = {"System Profile", "Guest Profile"}

# Paths
USER_DATA_PATH = os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\User Data')
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "active_profiles.json")
SNAPSHOT_PATH = os.path.join(SCRIPT_DIR, "extension_snapshot.json")
LOG_PATH = os.path.join(SCRIPT_DIR, "chrome_monitor.log")
LOCK_PATH = os.path.join(SCRIPT_DIR, "chrome_monitor.lock")

PROFILE_FILES = ['Preferences', 'Current Session', 'Current Tabs', 'History', 'Web Data']

# location codes in Chrome's extensions.settings: 4 == unpacked (developer mode)
LOC_UNPACKED = 4

_lock_fh = None


# --------------------------------------------------------------------------- #
# Lock / log
# --------------------------------------------------------------------------- #
def acquire_lock():
    global _lock_fh
    try:
        _lock_fh = open(LOCK_PATH, 'w')
        msvcrt.locking(_lock_fh.fileno(), msvcrt.LK_NBLCK, 1)
        _lock_fh.write(str(os.getpid()))
        _lock_fh.flush()
        return True
    except (IOError, OSError):
        if _lock_fh:
            _lock_fh.close()
            _lock_fh = None
        return False


def release_lock():
    global _lock_fh
    if _lock_fh:
        try:
            msvcrt.locking(_lock_fh.fileno(), msvcrt.LK_UNLCK, 1)
        except Exception:
            pass
        _lock_fh.close()
        _lock_fh = None
    try:
        os.remove(LOCK_PATH)
    except Exception:
        pass


def rotate_log():
    try:
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > LOG_MAX_BYTES:
            backup = LOG_PATH + ".1"
            if os.path.exists(backup):
                os.remove(backup)
            os.rename(LOG_PATH, backup)
    except Exception:
        pass


def log(message):
    rotate_log()
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    msg = f"[{timestamp}] {message}"
    print(msg)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Chrome process detection
# --------------------------------------------------------------------------- #
def is_chrome_running():
    """Return True/False, or None if the state could not be determined.

    None means "don't know" — the caller must NOT treat it as a crash, which
    avoids the spurious restarts the old tasklist-only check caused.
    """
    # Preferred: psutil (reliable, no shell-out flakiness).
    try:
        import psutil
        for proc in psutil.process_iter(['name']):
            try:
                if (proc.info['name'] or '').lower() == 'chrome.exe':
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False
    except ImportError:
        pass
    except Exception as e:
        log(f"psutil check failed ({e}); falling back to tasklist")

    # Fallback: tasklist. On the intermittent 0xC000041D failure, return None
    # (unknown) instead of False so we never falsely conclude Chrome crashed.
    try:
        output = subprocess.check_output(
            ['tasklist', '/FI', 'IMAGENAME eq chrome.exe', '/NH'],
            text=True, stderr=subprocess.DEVNULL
        )
        return "chrome.exe" in output.lower()
    except Exception as e:
        log(f"Error checking tasklist: {e}")
        return None


# --------------------------------------------------------------------------- #
# Profiles
# --------------------------------------------------------------------------- #
def get_active_profiles():
    active = []
    now = time.time()
    if not os.path.exists(USER_DATA_PATH):
        return active
    try:
        for name in os.listdir(USER_DATA_PATH):
            if name in IGNORED_PROFILES:
                continue
            full_path = os.path.join(USER_DATA_PATH, name)
            if not os.path.isdir(full_path):
                continue
            if not os.path.exists(os.path.join(full_path, 'Preferences')):
                continue
            for file_name in PROFILE_FILES:
                file_path = os.path.join(full_path, file_name)
                if os.path.exists(file_path):
                    if now - os.path.getmtime(file_path) <= ACTIVE_THRESHOLD:
                        active.append(name)
                        break
    except Exception as e:
        log(f"Error scanning profiles: {e}")
    return active


def save_active_profiles(profiles):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(profiles, f, indent=4)
    except Exception as e:
        log(f"Error saving profiles: {e}")


def load_active_profiles():
    if not os.path.exists(CONFIG_PATH):
        return []
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [p for p in data if p not in IGNORED_PROFILES]
    except Exception as e:
        log(f"Error loading profiles: {e}")
        return []


# --------------------------------------------------------------------------- #
# Unpacked-extension discovery + snapshot
# --------------------------------------------------------------------------- #
def _resolve_ext_name(ext_path, fallback):
    """Resolve an extension's display name from its manifest (+ _locales)."""
    try:
        import re
        manifest = os.path.join(ext_path, "manifest.json")
        m = json.load(open(manifest, encoding="utf-8-sig"))
        name = m.get("name", "") or fallback
        mm = re.match(r"__MSG_(\w+)__", name)
        if mm:
            key = mm.group(1)
            for loc in (m.get("default_locale", "en"), "en", "en_US"):
                mp = os.path.join(ext_path, "_locales", loc, "messages.json")
                if os.path.exists(mp):
                    msgs = json.load(open(mp, encoding="utf-8-sig"))
                    if key in msgs:
                        return msgs[key]["message"]
        return name
    except Exception:
        return fallback


def get_unpacked_extensions(profile):
    """Return {ext_id: {path, name, enabled}} for unpacked extensions in a
    profile, read from its Secure Preferences (where Chrome stores ext state)."""
    result = {}
    for fname in ("Secure Preferences", "Preferences"):
        sp = os.path.join(USER_DATA_PATH, profile, fname)
        if not os.path.exists(sp):
            continue
        try:
            d = json.load(open(sp, encoding="utf-8"))
        except Exception:
            continue
        settings = d.get("extensions", {}).get("settings", {})
        chrome_dir = os.path.dirname(CHROME_PATH).lower()
        for eid, info in settings.items():
            path = info.get("path", "")
            loc = info.get("location")
            # Only true unpacked (developer-mode) extensions: location 4 with an
            # absolute path that is NOT one of Chrome's bundled component exts
            # (those live under the Chrome install dir, location 5).
            if loc != LOC_UNPACKED:
                continue
            if not os.path.isabs(path):
                continue
            if path.lower().startswith(chrome_dir):
                continue
            # state: 1 == enabled, 0 == disabled (absent == treat as enabled)
            enabled = info.get("state", 1) != 0
            result[eid] = {
                "path": path,
                "name": _resolve_ext_name(path, info.get("manifest", {}).get("name", eid)),
                "enabled": enabled,
            }
    return result


def snapshot_extensions(profiles):
    """Record the unpacked extensions currently present for each active profile,
    so a later restore knows what SHOULD be loaded."""
    snap = load_snapshot()
    for p in profiles:
        exts = get_unpacked_extensions(p)
        if exts:
            snap[p] = exts
    try:
        with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
            json.dump(snap, f, indent=4)
    except Exception as e:
        log(f"Error saving extension snapshot: {e}")


def load_snapshot():
    if not os.path.exists(SNAPSHOT_PATH):
        return {}
    try:
        with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def missing_extension_paths(profile, snapshot):
    """Return the on-disk paths of unpacked extensions that the snapshot says
    should be loaded but are currently absent/disabled — i.e. need reloading."""
    expected = snapshot.get(profile, {})
    if not expected:
        return []
    current = get_unpacked_extensions(profile)
    missing = []
    for eid, info in expected.items():
        path = info.get("path", "")
        if not path or not os.path.exists(path):
            continue  # source folder gone — can't reload it
        cur = current.get(eid)
        if cur is None or not cur.get("enabled", True):
            missing.append(path)
    return missing


# --------------------------------------------------------------------------- #
# Launch
# --------------------------------------------------------------------------- #
def chrome_cmd():
    return CHROME_PATH if os.path.exists(CHROME_PATH) else "chrome.exe"


def launch_profile(profile_name, load_extension_paths=None):
    cmd = [chrome_cmd(), f'--profile-directory={profile_name}']
    if load_extension_paths:
        cmd.append('--load-extension=' + ",".join(load_extension_paths))
        log(f"Launching profile '{profile_name}' + reloading {len(load_extension_paths)} extension(s)")
    else:
        log(f"Launching Chrome profile: {profile_name}")
    try:
        subprocess.Popen(cmd, start_new_session=True)
    except Exception as e:
        log(f"Failed to launch profile {profile_name}: {e}")


# --------------------------------------------------------------------------- #
# Window discovery + arrangement (win32)
# --------------------------------------------------------------------------- #
def get_chrome_windows():
    """Return a list of HWNDs for real Chrome browser windows."""
    try:
        import win32gui
    except Exception as e:
        log(f"win32gui unavailable, cannot manage windows: {e}")
        return []

    handles = []

    def _cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        if win32gui.GetClassName(hwnd) != "Chrome_WidgetWin_1":
            return
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return
        l, t, r, b = win32gui.GetWindowRect(hwnd)
        if (r - l) < 400 or (b - t) < 300:   # skip tooltips / popups / chrome plumbing
            return
        handles.append(hwnd)

    win32gui.EnumWindows(_cb, None)
    return handles


def wait_for_windows(expected, timeout=WINDOW_WAIT_TIMEOUT):
    """Poll until at least `expected` Chrome windows exist (or timeout)."""
    deadline = time.time() + timeout
    last = 0
    while time.time() < deadline:
        wins = get_chrome_windows()
        last = len(wins)
        if last >= expected:
            log(f"All {last} Chrome window(s) present.")
            return wins
        time.sleep(1)
    log(f"Window wait timed out: {last}/{expected} window(s) appeared.")
    return get_chrome_windows()


def arrange_windows(handles):
    """Tile the given windows in a grid across the primary monitor work area."""
    if not handles:
        return
    try:
        import win32gui
        import win32con
        import win32api
    except Exception as e:
        log(f"win32 unavailable, skipping arrange: {e}")
        return

    work = win32api.GetMonitorInfo(
        win32api.MonitorFromPoint((0, 0))
    )["Work"]
    wx, wy, wr, wb = work
    width, height = wr - wx, wb - wy

    n = len(handles)
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    cell_w = width // cols
    cell_h = height // rows

    handles = sorted(handles)  # stable order
    for i, hwnd in enumerate(handles):
        col = i % cols
        row = i // cols
        x = wx + col * cell_w
        y = wy + row * cell_h
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.MoveWindow(hwnd, x, y, cell_w, cell_h, True)
        except Exception as e:
            log(f"Failed to move window {hwnd}: {e}")
    log(f"Arranged {n} window(s) in a {cols}x{rows} grid.")


# --------------------------------------------------------------------------- #
# Click the extension toolbar buttons (UI Automation)
# --------------------------------------------------------------------------- #
def click_extensions(handles, names=None):
    """In each Chrome window, click the toolbar button(s) whose accessible name
    contains one of `names`. Returns the number of clicks performed."""
    names = names or CLICK_EXTENSIONS
    try:
        import uiautomation as auto
    except Exception as e:
        log(f"uiautomation unavailable, skipping extension clicks: {e}")
        return 0

    clicks = 0
    auto.SetGlobalSearchTimeout(2)
    for hwnd in handles:
        try:
            win = auto.ControlFromHandle(hwnd)
            if not win:
                continue
            win.SetActive()
            for name in names:
                btn = win.ButtonControl(SubName=name)
                if btn.Exists(2, 0.2):
                    btn.Click(simulateMove=False, waitTime=0.2)
                    clicks += 1
                    log(f"Clicked extension '{name}' in window '{win.Name[:40]}'.")
        except Exception as e:
            log(f"Click failed on window {hwnd}: {e}")
    if clicks == 0:
        log(f"No matching extension buttons found for {names}.")
    return clicks


# --------------------------------------------------------------------------- #
# The full ordered restore sequence
# --------------------------------------------------------------------------- #
def restore_and_setup(profiles):
    """Open -> wait -> arrange -> click, strictly in order, each step logged."""
    snapshot = load_snapshot()

    # STEP 1 — open every profile, reloading removed/disabled unpacked exts.
    log(f"STEP 1/4 — Opening {len(profiles)} profile(s): {profiles}")
    for p in profiles:
        missing = missing_extension_paths(p, snapshot)
        if missing:
            log(f"  Profile '{p}': extensions removed/disabled, reloading: {missing}")
        launch_profile(p, load_extension_paths=missing or None)
        time.sleep(LAUNCH_DELAY)

    # STEP 2 — wait for the windows to actually appear.
    log("STEP 2/4 — Waiting for Chrome windows to appear...")
    windows = wait_for_windows(len(profiles))
    if not windows:
        log("No Chrome windows detected; aborting arrange/click steps.")
        return
    time.sleep(WINDOW_SETTLE)
    windows = get_chrome_windows()

    # STEP 3 — arrange the windows in a grid.
    log("STEP 3/4 — Arranging windows...")
    arrange_windows(windows)
    time.sleep(1.5)

    # STEP 4 — click the configured extension toolbar buttons.
    log("STEP 4/4 — Clicking extensions...")
    click_extensions(windows, CLICK_EXTENSIONS)

    log("Restore sequence complete.")


# --------------------------------------------------------------------------- #
# Main loop
# --------------------------------------------------------------------------- #
def main():
    if not acquire_lock():
        print("Chrome Monitor is already running. Exiting.")
        sys.exit(1)

    import atexit
    atexit.register(release_lock)

    log("Chrome Auto-Restart Monitor started.")
    last_active = load_active_profiles()
    log(f"Loaded active profiles cache: {last_active}")

    last_restore_time = 0

    while True:
        try:
            running = is_chrome_running()

            if running is True:
                current_active = get_active_profiles()
                if current_active:
                    current_active.sort()
                    if current_active != last_active:
                        log(f"Active profiles changed: {current_active}")
                        save_active_profiles(current_active)
                        last_active = current_active
                    # Keep the unpacked-extension snapshot fresh while running.
                    snapshot_extensions(current_active)

            elif running is False:
                now = time.time()
                if now - last_restore_time < RESTORE_COOLDOWN:
                    pass  # still in cooldown after last restore
                else:
                    to_restore = load_active_profiles()
                    if to_restore:
                        log(f"Chrome closed/crashed. Restoring {len(to_restore)} "
                            f"profile(s): {to_restore}")
                        last_restore_time = now
                        restore_and_setup(to_restore)
                        last_active = to_restore
            # running is None -> state unknown; do nothing (no false restart).

        except Exception as e:
            log(f"Error in monitor loop: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--check":
        print(f"Active profiles: {get_active_profiles()}")
        sys.exit(0)
    if arg == "--snapshot":
        profs = get_active_profiles()
        snapshot_extensions(profs)
        print(f"Snapshotted unpacked extensions for: {profs}")
        print(json.dumps(load_snapshot(), indent=2))
        sys.exit(0)
    if arg == "--run-now":
        # Manually run the full open->arrange->click sequence (for testing).
        profs = load_active_profiles() or get_active_profiles()
        if not profs:
            print("No profiles to restore.")
            sys.exit(1)
        restore_and_setup(profs)
        sys.exit(0)
    if arg == "--arrange":
        arrange_windows(get_chrome_windows())
        sys.exit(0)
    if arg == "--click":
        click_extensions(get_chrome_windows(), CLICK_EXTENSIONS)
        sys.exit(0)
    main()
