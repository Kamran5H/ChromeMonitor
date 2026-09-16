# 🔍 Chrome Monitor

<div align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D6?style=for-the-badge&logo=windows&logoColor=white)](https://github.com/Kamran5H/ChromeMonitor)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://github.com/Kamran5H/ChromeMonitor)
[![Architecture](https://img.shields.io/badge/Design-Single--Instance%20Daemon-10B981?style=for-the-badge)](https://github.com/Kamran5H/ChromeMonitor)
[![Audit](https://img.shields.io/badge/Audit-Profile%20%26%20Extension%20Tracker-EC4899?style=for-the-badge)](https://github.com/Kamran5H/ChromeMonitor)

**A lightweight, single-instance Windows background utility that audits active Google Chrome profiles, installed extensions, and process lifecycles.**

[Features](#-key-features) • [Installation](#-installation--service-setup) • [Architecture](#-architecture) • [Files](#-repository-structure) • [License](#-license)

</div>

---

## 🌟 Executive Overview

**Chrome Monitor** is a dedicated Windows system administration and security monitoring utility written in Python. It watches the local Google Chrome user data directory (`%LOCALAPPDATA%\Google\Chrome\User Data`), tracks which browser profiles are concurrently active, monitors extensions installed or loaded into each profile, and maintains an auditable timeline log.

Engineered for stability, Chrome Monitor utilizes Windows inter-process lock files to strictly prevent duplicate instances, provides silent `.vbs` background execution, and ships with turnkey startup registration scripts.

---

## 🚀 Key Features

- **👥 Multi-Profile Tracking**: Scans and parses `Local State` and profile directories (`Default`, `Profile 1`, etc.) to detect active user sessions.
- **🧩 Extension Inventory & Change Detection**: Generates structured snapshots (`extension_snapshot.json`) of all installed extensions, IDs, version numbers, and permissions, flagging unexpected additions.
- **🔒 Single-Instance Guarantee**: Implements robust Windows file-locking primitives so only one daemon process runs at any given time.
- **🔕 Silent Background Operation**: Lauched via `start_monitor.vbs` without opening an intrusive command prompt console.
- **📝 Comprehensive Automation Logging**: Maintains timestamped records in `@AutomationLog.txt` tracking launch events, profile switches, and shutdown hooks.
- **⚡ Startup Automation**: Turnkey `.bat` scripts to install or remove the monitor from the Windows user startup registry or folder.

---

## 🏗️ Architecture

```mermaid
flowchart LR
    A[Windows Startup / User Trigger] --> B[start_monitor.vbs]
    B --> C[chrome_monitor.py Daemon]
    C -->|Single-Instance Check| D{Lock File Active?}
    D -- Yes --> E[Exit Silently]
    D -- No --> F[Acquire Lock]
    F --> G[Inspect Chrome User Data]
    G --> H[(active_profiles.json)]
    G --> I[(extension_snapshot.json)]
    G --> J[Append to @AutomationLog.txt]
```

---

## 📁 Repository Structure

```text
ChromeMonitor/
├── chrome_monitor.py           # Core monitoring daemon & profile inspection engine
├── active_profiles.json        # Live serialized state of currently active profiles
├── extension_snapshot.json     # Comprehensive catalog of installed extensions & versions
├── @AutomationLog.txt          # Continuous system audit log
├── start_monitor.vbs           # Silent VBScript background launcher
├── install_startup.bat         # Turnkey batch script to register Windows startup
├── stop_monitor.bat            # Graceful process terminator script
├── .gitignore                  # Python & Windows runtime exclusions
└── LICENSE                     # Open-source MIT License
```

---

## ⚡ Installation & Service Setup

### 1. Manual Launch
```bash
# Run in terminal
python chrome_monitor.py

# Or launch silently in background
start_monitor.vbs
```

### 2. Auto-Start with Windows
1. Double-click [`install_startup.bat`](install_startup.bat) to place a launcher shortcut in your Windows Startup directory (`shell:startup`).
2. Chrome Monitor will now quietly initialize every time you log into Windows.

### 3. Stop Monitor
Double-click [`stop_monitor.bat`](stop_monitor.bat) to release the lock and terminate the running monitor process.

---

## 📜 License

This project is open-source and released under the [MIT License](LICENSE).  
Copyright (c) 2024-2026 **Kamran Ashraf**.
