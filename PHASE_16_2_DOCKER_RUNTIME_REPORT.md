# Phase 16.2 — Docker Runtime Setup & Genuine Integration Audit Report

**Document Version:** 1.0.0  
**Phase:** Phase 16.2 — Docker Runtime Setup and Genuine Integration  
**Repository:** [https://github.com/HMSLBDN/Autoheal.git](https://github.com/HMSLBDN/Autoheal.git)  
**Branch:** `main`  
**Current Baseline Commit:** `33d58d9ea164e70c5732fce15200f888b477af12`  
**Audit Timestamp:** 2026-11-22T08:10:15Z  
**Verification Status:** **BLOCKED** (Docker Desktop not installed / inactive on Windows host)  
**Safety Mandate:** `RECOVERY_SIMULATION_MODE=true` (Active Default Hard Lock)  

---

## 1. Executive Summary & Verification Outcome

In accordance with Phase 16.2 requirements, a comprehensive environment audit of the Windows host system and WSL2 runtime was conducted to verify Docker daemon connectivity prior to attempting live container lifecycle operations.

### Executive Verdict: **BLOCKED**
- **Docker CLI on Windows PATH:** **NOT DETECTED** (`where docker` returned exit code 1).
- **Docker Compose CLI on PATH:** **NOT DETECTED** (`where docker-compose` returned exit code 1).
- **Docker Processes:** **ZERO ACTIVE** (`Get-Process *docker*` returned 0 processes).
- **Windows Services:** **ZERO REGISTERED** (`Get-Service *docker*` returned 0 services).
- **Docker Desktop Installation Paths:** **ABSENT** (`C:\Program Files\Docker\Docker`, `C:\ProgramData\DockerDesktop`, and user profile directories do not exist).
- **Windows Registry:** **NO REGISTRATION** (`HKLM\Software\Docker Inc.` and `HKCU\Software\Docker Inc.` not found).
- **WSL2 Integration:** Distribution `Ubuntu` exists (Version 2) in state `Stopped`. The Docker Desktop WSL2 integration distributions (`docker-desktop`, `docker-desktop-data`) are absent.
- **Docker Named Pipes:** **ZERO FOUND** (`\\.\pipe\` contains no active Docker daemon pipes).

### Strict Scientific Integrity Statement:
In strict compliance with the Phase 16.2 mandate:
> *"If actual Docker is unavailable, report BLOCKED. Never use the mock engine to claim a live recovery. Do not continue to the live integration tests until daemon connectivity is genuine."*

Live recovery operations (Steps 4 and 5) have **not** been executed. The mock engine has deliberately **not** been used to simulate recovery for this report. Live Docker verification remains **BLOCKED** pending user installation and startup of Docker Desktop.

---

## 2. Environment Diagnostics (Step 1 Audit Evidence)

The environment audit script (`audit_docker_env.py`) executed the following system queries with unconstrained host permissions:

### 1. Windows CLI Availability
```powershell
where docker
# Result: Exit code 1
# INFO: Could not find files for the given pattern(s).

where docker-compose
# Result: Exit code 1
# INFO: Could not find files for the given pattern(s).
```

### 2. Running Process Diagnostics
```powershell
Get-Process *docker* -ErrorAction SilentlyContinue | Select-Object Id, ProcessName, Path
# Result: Empty (0 processes running)
```

### 3. Windows Services Status
```powershell
Get-Service *docker* -ErrorAction SilentlyContinue | Select-Object Name, Status, DisplayName
# Result: Empty (0 services registered)
```

### 4. Standard Installation Directory Inspection
```text
C:\Program Files\Docker\Docker\Docker Desktop.exe              -> exists: False
C:\Program Files\Docker\Docker\resources\bin\docker.exe        -> exists: False
C:\Program Files\Docker\Docker\resources\bin\docker-compose.exe-> exists: False
C:\ProgramData\DockerDesktop                                   -> exists: False
C:\Users\aksha\AppData\Local\Programs\DockerDesktop\Docker Desktop.exe -> exists: False
C:\Users\aksha\AppData\Local\Docker                           -> exists: False
C:\Program Files (x86)\Docker                                  -> exists: False
```

### 5. Windows Registry Keys
```powershell
reg query "HKLM\Software\Docker Inc." /s
# Result: Exit code 1 (ERROR: The system was unable to find the specified registry key or value.)

reg query "HKCU\Software\Docker Inc." /s
# Result: Exit code 1 (ERROR: The system was unable to find the specified registry key or value.)
```

### 6. WSL2 Subsystem Status
```powershell
wsl -l -v
# Output:
#   NAME      STATE      VERSION
# * Ubuntu    Stopped    2

wsl -e which docker
# Result: Exit code 1 (no docker binary found in Ubuntu PATH)
```

### 7. Named Pipe IPC Check
```python
import glob
pipes = [p for p in glob.glob(r"\\.\pipe\*") if "docker" in p.lower()]
# Result: [] (Zero Docker pipes active)
```

---

## 3. Official User Instructions: How to Install & Start Docker Desktop

Because Docker Desktop is completely absent from the host machine, it must be installed interactively by the user. In accordance with safety rules, the agent will **not** attempt silent or automated system software installation.

### Step-by-Step Installation Instructions for the User:

1. **Download Official Installer:**
   - Download the official Docker Desktop for Windows installer:  
     👉 [https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe](https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe)

2. **Run Installer:**
   - Launch `Docker Desktop Installer.exe`.
   - Ensure the checkbox **"Use WSL 2 instead of Hyper-V (recommended)"** is **checked**.
   - Complete the installation wizard and restart your computer if prompted.

3. **Launch Docker Desktop:**
   - From the Windows Start menu, launch **Docker Desktop**.
   - Accept the Docker Subscription Service Agreement.
   - Wait until the Docker Desktop status indicator in the bottom-left corner turns **green** (**"Engine running"**).

4. **Verify WSL 2 Integration:**
   - In Docker Desktop, open **Settings** (gear icon) $\to$ **Resources** $\to$ **WSL Integration**.
   - Ensure **"Enable integration with my default WSL distro"** is checked, and toggle on integration for **Ubuntu**.
   - Click **Apply & restart**.

5. **Confirm CLI Availability:**
   - Open a fresh PowerShell terminal and run:
     ```powershell
     docker --version
     docker compose version
     docker ps
     ```
   - All three commands should exit with code 0.

---

## 4. Requirement 3: Audit of Docker Agent Access & Socket Security

### Inspection of `docker-compose.test-infra.yml`

```yaml
version: '3.8'

networks:
  autoheal_test_network:
    driver: bridge
    name: autoheal_test_network

services:
  autoheal_test_service:
    build:
      context: .
      dockerfile: test_environment/Dockerfile.test_service
    container_name: autoheal_test_service
    hostname: autoheal_test_service
    ports:
      - "8086:8080"
    networks:
      - autoheal_test_network

  autoheal_docker_agent:
    build:
      context: .
      dockerfile: test_environment/Dockerfile.agent
    container_name: autoheal_docker_agent
    hostname: autoheal_docker_agent
    ports:
      - "8091:8091"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    networks:
      - autoheal_test_network
```

### Critical Security Analysis: The Read-Only Socket Illusion

> [!WARNING]
> Mounting `/var/run/docker.sock` with the `:ro` flag does **NOT** restrict Docker Engine API operations to read-only queries.

#### Why `:ro` Does Not Protect the Host:
- The Docker socket is a Unix domain socket (IPC communication endpoint).
- The Linux VFS `:ro` mount flag prevents modifying the *inode attributes* or unlinking the socket file from the filesystem.
- However, opening a connection to an existing domain socket and transmitting HTTP byte streams (`POST /containers/{id}/restart`, `POST /containers/create`, `DELETE /containers/{id}`) is handled by the Docker daemon running on the host as root.
- The host daemon executes whatever HTTP API command is sent across the socket regardless of the container mount's read-only flag.
- Therefore, **mounting `/var/run/docker.sock` into any container grants that container root-equivalent execution over the Docker Engine.**

### Safest Feasible Local Architecture:

To harden the local test environment before production deployment:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        FastAPI Control Plane                           │
│                     (ZERO DOCKER SOCKET ACCESS)                        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Authenticated HTTP API (Port 8091)
┌───────────────────────────────────▼────────────────────────────────────┐
│              Dedicated Isolated Test Network Mesh                      │
│                   (autoheal_test_network)                              │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ Restricted Docker Recovery Agent (docker_agent)                  │  │
│  │  - Server-Side Container Allowlist: ONLY autoheal_test_service   │  │
│  │  - Server-Side Operation Allowlist: restart_container, inspect   │  │
│  │  - Two-Stage Verification: Stage 1 Restart, Stage 2 HTTP Probe   │  │
│  └────────────────────────────────┬─────────────────────────────────┘  │
│                                   │ HTTP API via Proxy                 │
│  ┌────────────────────────────────▼─────────────────────────────────┐  │
│  │ Docker Socket Proxy (tecnativa/docker-socket-proxy)              │  │
│  │  - Strips all destructive endpoints                             │  │
│  │  - Enforces: POST=0 (Default Deny), CONTAINERS=1, RESTART=1      │  │
│  │  - BLOCKS: VOLUMES=0, NETWORKS=0, IMAGES=0, EXEC=0, SWARM=0      │  │
│  └────────────────────────────────┬─────────────────────────────────┘  │
│                                   │ Unix Domain Socket                 │
│                                   ▼                                    │
│                     Host Docker Daemon (/var/run/docker.sock)          │
└────────────────────────────────────────────────────────────────────────┘
```

#### Production Architecture Recommendation:
1. **Docker Socket Proxy:** Interpose a dedicated socket proxy container between the agent and `/var/run/docker.sock`. Configure environment:
   ```yaml
   CONTAINERS: 1
   POST: 0
   RESTART: 1
   BUILD: 0
   COMMIT: 0
   EXEC: 0
   IMAGES: 0
   INFO: 1
   NETWORKS: 0
   NODES: 0
   PLUGINS: 0
   SERVICES: 0
   SESSION: 0
   SWARM: 0
   SYSTEM: 0
   TASKS: 0
   VOLUMES: 0
   ```
2. **Explicit Statement:** The direct socket mount `/var/run/docker.sock:/var/run/docker.sock:ro` in `docker-compose.test-infra.yml` is **NOT production-safe** and must **NEVER** be used outside the isolated local test mesh.

---

## 5. Live Recovery Test Status (Steps 4 & 5)

| Step | Target | Status | Reason / Evidence |
| :--- | :--- | :---: | :--- |
| **Step 2 — Verify Docker Runtime** | Host Docker Engine | **BLOCKED** | Docker daemon is not running on host. |
| **Step 4 — Start Isolated Test Stack** | `autoheal_test_service`, `autoheal_docker_agent` | **BLOCKED** | Cannot launch containers without Docker daemon. |
| **Step 5 — Genuine Recovery Test** | Container restart + health check | **BLOCKED** | Cannot perform live Docker container lifecycle operations. |
| **Step 6 — Negative Security Tests** | Protected container rejection | **VERIFIED (IN-CODE & TESTS)** | Verified in unit test suite (`test_phase16_docker_agent.py`, 19 passing tests). |

---

## 6. Simulation Mode & Safety Safeguards (Step 7)

All safety rules remain fully intact and enforced:
- `RECOVERY_SIMULATION_MODE=true` remains the default in `backend/app/config.py`.
- `RESTRICTED_DOCKER_AGENT_ENABLED=false` remains the default in `backend/app/config.py`.
- No modifications were made to core services (`db`, `redis`, `backend`, `frontend`, `prometheus`, `grafana`).
- Zero database volumes deleted.
- Zero deployments or cloud provisioning performed.
- Zero git commits or pushes performed.

---

## 7. Next Steps to Unblock Live Verification

1. **User Action:** Install and launch Docker Desktop on the Windows host following the instructions in Section 3.
2. **Once Docker Desktop is Running:** Run `docker ps` in terminal to confirm daemon readiness.
3. **Agent Action:** Upon user confirmation that Docker Desktop is active, proceed to Step 2 (`docker --version`, `docker compose version`, `docker info`), launch `docker-compose.test-infra.yml`, and execute the genuine end-to-end recovery test against `autoheal_test_service`.
