# WINDOWS DOCKER DESKTOP RUNTIME INVESTIGATION & MANUAL RECOVERY GUIDE

**Project:** AutoHeal DevOps SaaS  
**Host Platform:** Windows 11 Enterprise (x86_64)  
**Docker Version:** 29.9.3 (Build 5457199), Compose v5.7.0  
**WSL2 Kernel:** 6.18.33.2-microsoft-standard-WSL2  
**Status:** **INVESTIGATED & DIAGNOSED** (Requires Interactive Windows Desktop Session)

---

## 1. System Environment Audit Findings

| Component | Verified State | Observed Diagnostic Value |
| :--- | :--- | :--- |
| **Windows OS** | Windows 11 Enterprise (Build 26100) | `DESKTOP-H1N514E\Akshay N` |
| **CPU Virtualization** | Intel Core Ultra 5 226V (8 Cores) | VirtualizationFirmwareEnabled: `True` (SLAT Active) |
| **Available RAM** | 15.66 GB Total / 3.71 GB Available | Sufficient for all 14 local containers |
| **Available Disk** | 227.82 GB Free on `C:` Drive | Substantially exceeds Docker minimum requirements |
| **WSL2 Subsystem** | Operational | Default distribution: `Ubuntu-24.04`, Version: 2 |
| **Windows Services** | Running | `vmcompute` (Hyper-V) & `WSLService` (WSL) Active |
| **Docker Binary Path**| Found | `C:\Users\Akshay N\AppData\Local\Programs\DockerDesktop\Docker Desktop.exe` |
| **Docker Named Pipe** | Inactive in Headless Session | `//./pipe/dockerDesktopLinuxEngine` (File not found) |

---

## 2. Root Cause Analysis: Why Docker Cannot Run Headlessly

Detailed inspection of Docker Desktop's process execution and logs in `C:\Users\Akshay N\AppData\Local\Docker\log\host\com.docker.backend.exe.log` revealed:

```
[com.docker.backend.exe.apiproxy] serving the Linux engine on \\.\pipe\dockerDesktopLinuxEngine
[com.docker.backend.exe.apiproxy] closing \\.\pipe\dockerDesktopLinuxEngine
```

### The Architectural Constraint:
1. Docker Desktop on Windows is an **interactive Electron/WPF desktop application**, not a background headless Windows service.
2. When launched from an automated CLI sub-agent session without an interactive desktop UI window handle, the Electron UI process encounters a missing desktop session context and terminates.
3. Upon process termination, `com.docker.backend.exe` closes the named pipe `\\.\pipe\dockerDesktopLinuxEngine`.
4. Subsequent calls to `docker ps` or `docker compose up` fail with:
   ```
   open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.
   ```

---

## 3. Exact Manual Recovery Steps for the Windows Operator

To start the Docker daemon and bring the complete local container stack online:

```powershell
# Step 1: Open the Windows Start Menu, search for "Docker Desktop", and launch it.
# Or run from an interactive PowerShell terminal:
Start-Process "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe"

# Step 2: Wait 20-30 seconds until the Docker whale icon in the Windows taskbar tray becomes steady green ("Docker Desktop is running").

# Step 3: Open PowerShell and verify connectivity:
docker info

# Step 4: Verify that hello-world executes:
docker run --rm hello-world

# Step 5: Start the AutoHeal 14-service production-like compose stack:
cd "c:\Users\Akshay N\Documents\Autoheal\autoheal-devops-saas"
docker compose up -d --build

# Step 6: Verify all services are healthy:
docker compose ps
```
