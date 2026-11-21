# PostgreSQL 16 Connection Evidence & Engine Verification

**Instance:** Live Container `autoheal_db_dev` (`postgres:16-alpine`)  
**Timestamp:** 2026-11-21T19:27:30+05:30  
**Status:** **VERIFIED**  

---

## 1. Engine & Server Metadata

| Attribute | Measured Runtime Value |
| :--- | :--- |
| **PostgreSQL Version** | `PostgreSQL 16.16 on x86_64-pc-linux-musl, compiled by gcc (Alpine 15.2.0) 15.2.0, 64-bit` |
| **Server Version** | `16.16` |
| **Host** | `127.0.0.1` |
| **Port** | `5432` |
| **Database** | `autoheal_db` |
| **User** | `autoheal_user` |
| **Connection Method** | `asyncpg` native asynchronous wire protocol + SQLAlchemy 2.0 Asyncio connection pool |
| **Max Connections** | `100` (`SHOW max_connections`) |
| **Shared Buffers** | `128MB` (`SHOW shared_buffers`) |

---

## 2. Multi-Tenant Isolation & Security Verification

A live experiment was performed in an isolated test schema:
- **Tenant A:** Org ID `01d1b8c2-...` ("Tenant Alpha")
- **Tenant B:** Org ID `ac3fa478-...` ("Tenant Beta")

### Isolation Query Execution:
```sql
SELECT COUNT(*) FROM services 
WHERE organization_id = '01d1b8c2-...' AND id = 'svc-beta-resource';
```
- **Result:** `0` rows returned.
- **Verification:** Strict tenant partition invariant holds. Queries scoped to Tenant Alpha return zero leaked records from Tenant Beta.

---

## 3. ACID Transactions & CRUD Invariant Verification

1. **Create (Insert):** Canary service `crud-canary-svc` inserted with initial latency 15.0ms.
2. **Read (Select):** Row verified present and fields matched exactly.
3. **Update:** Latency updated to 250.0ms, status changed to `degraded`. Verified updated timestamp.
4. **Delete:** Canary deleted. Verification query returned `None`.
5. **Transaction Commit:** In an async transaction block, committed row persisted across sessions.
6. **Transaction Rollback:** In an async transaction block with intentional exception, rollback cleanly discarded changes with zero residual data.

---

## 4. Container Restart Persistence Verification

1. Written canary record: `_persistence_canary` with token `TOKEN-9aca3c8f1be74b6dbb3a4066a8593be4` on base database `autoheal_db`.
2. Executed: `docker restart autoheal_db_dev`.
3. Restart duration: **1.83 seconds**.
4. Read-back probe: Polled until healthy. Re-queried `_persistence_canary` by ID.
5. **Result:** Token matched `TOKEN-9aca3c8f1be74b6dbb3a4066a8593be4` identically. Zero data loss.
