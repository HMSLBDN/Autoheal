# Docker Desktop Activation Results

**Date:** 2026-11-21  
**Operating System:** Windows 11 Enterprise (64-bit)  
**Status:** **VERIFIED & OPERATIONAL**  

---

## 1. Environment & Daemon Diagnostics

Following manual user activation from the Windows desktop GUI, Docker Desktop established its interactive user-session daemon handle, initialized the WSL2 Linux engine, and bound the named pipe endpoint.

### Command Execution Evidence

#### 1. `docker version`
```text
Client:
 Version:           29.9.3
 API version:       1.56
 Go version:        go1.26.10
 Git commit:        5457199
 Built:             Tue Nov  3 21:46:10 2026
 OS/Arch:           windows/amd64
 Context:           desktop-linux

Server: Docker Desktop 4.99.0 (245822)
 Engine:
  Version:          29.9.3
  API version:      1.56 (minimum version 1.40)
  Go version:       go1.26.10
  Git commit:       70efc0e
  Built:            Tue Nov  3 21:41:42 2026
  OS/Arch:          linux/amd64
  Experimental:     false
 containerd:
  Version:          v2.4.2
 runc:
  Version:          1.5.2
 docker-init:
  Version:          0.19.0
```

#### 2. `docker info`
- **Server Version:** `29.9.3`
- **Kernel Version:** `6.18.33.2-microsoft-standard-WSL2`
- **Operating System:** `Docker Desktop`
- **CPUs Allocated:** `8`
- **Total Memory Allocated:** `7.586 GiB`
- **Named Pipe Address:** `npipe:////./pipe/dockerDesktopLinuxEngine`
- **Default Storage Driver:** `overlayfs` (`io.containerd.snapshotter.v1`)
- **Cgroup Version:** `2`

#### 3. `docker compose version`
```text
Docker Compose version v5.7.0
```

#### 4. `docker ps`
Verified 14 running containers active across `autoheal_network` and `autoheal_dev_network`.
Zero errors returned. Named pipe connection established without failure.
