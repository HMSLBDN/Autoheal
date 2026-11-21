# WINDOWS DOCKER DESKTOP & WSL2 DIAGNOSTICS & SETUP GUIDE

**Project:** AutoHeal DevOps SaaS  
**Host Platform:** Windows 11 Enterprise (x86_64)  
**Hardware Virtualization:** Intel Core Ultra 5 226V (SLAT Enabled, Hyper-V Active)  
**WSL2 Version:** 2.0 / Distribution: `Ubuntu-24.04`  
**Docker Version:** 29.9.3 (Build 5457199), Compose v5.7.0  
**Date:** 2026-11-21

---

## 1. Diagnostic Findings & Root Cause Analysis

During Phase 11 and Phase 12 validation runs, automated CLI commands targeting the Docker daemon encountered:

```
failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine:
open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.
```

### Technical Root Cause
1. **Interactive User-Mode Named Pipe Architecture:**  
   Docker Desktop on Windows does **not** run as an independent background Windows system service (`SYSTEM` account). Instead, it runs as an interactive user-mode application (`Docker Desktop.exe`) within the logged-in user's desktop session.
2. **Named Pipe Lifecycle:**  
   The named pipe `//./pipe/dockerDesktopLinuxEngine` is created only when the Docker Desktop GUI process initializes, mounts the WSL2 virtual disk (`ext4.vhdx`), and boots the `docker-desktop` distro.
3. **Headless / Background Agent Limitation:**  
   When autonomous developer agents or non-interactive build harnesses execute commands without an active desktop UI session, the named pipe remains uninstantiated.

---

## 2. Host Diagnostics Audit Results

```powershell
# 1. Hyper-V and Windows Subsystem for Linux Services
Status   Name        DisplayName
------   ----        -----------
Running  vmcompute   Hyper-V Host Compute Service
Running  WSLService  WSL Service

# 2. WSL Distribution States
NAME                   STATE      VERSION
Ubuntu-24.04           Running    2
docker-desktop         Stopped    2

# 3. Disk Space Verification
Drive C: Free Space: 244.6 GB (Used: 265.9 GB) -> PASS (> 20 GB required)

# 4. CPU Virtualization
Processor: Intel(R) Core(TM) Ultra 5 226V
VirtualizationFirmwareEnabled: True (SLAT Active) -> PASS
```

---

## 3. Manual Operator Steps to Start Docker Desktop

To bring the local Docker environment online on Windows:

```powershell
# Step 1: Launch Docker Desktop from the Windows Start Menu or Desktop
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
# Or if installed in user directory:
Start-Process "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe"

# Step 2: Wait for System Tray Whale Icon to become steady (green)

# Step 3: Verify Daemon Connectivity in PowerShell
docker info

# Step 4: Verify Docker Context
docker context use desktop-linux

# Step 5: Test Container Execution
docker run --rm hello-world
```

---

## 4. Troubleshooting Checklist

| Symptom | Cause | Solution |
| :--- | :--- | :--- |
| `The system cannot find the file specified` on named pipe | Docker Desktop process not running | Launch Docker Desktop from Start menu; wait 15s for whale icon to stabilize. |
| `WSL 2 installation is incomplete` | Outdated WSL2 Linux kernel | Run `wsl --update` in an administrative terminal. |
| `Virtualization disabled in firmware` | BIOS virtualization turned off | Enable Intel VT-x / AMD-V in motherboard BIOS. |
| Port conflicts (`5432` or `8000` already in use) | Background service binding host port | Stop conflicting service or use `docker compose -f docker-compose.dev.yml` with port remapping. |
