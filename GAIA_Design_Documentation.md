# GAIA-BASE Agent Design Documentation
## Smart Waste Management System (SWMS)

---

## 1. System Objective

The **Smart Waste Management System (SWMS)** is a Multi-Agent System (MAS) built on the DALI agent platform. Its objective is to automate the urban waste collection process through the coordinated cooperation of autonomous agents.

### Goal

The system monitors the fill level of distributed smart bins across a city. When a bin reaches maximum capacity, the system automatically orchestrates the dispatch of a collection truck, supervises the pickup lifecycle, and resets the bin to an operational state — without human intervention.

### Core Properties

| Property | Description |
|---|---|
| **Autonomy** | Each agent acts independently on the basis of its own internal state and received events |
| **Reactivity** | Agents respond to environment changes (fill level, truck availability, timeouts) |
| **Pro-activeness** | The control center anticipates failures via TTL-based timeout supervision |
| **Communication** | Agents exchange typed FIPA-like messages over shared token-authenticated channels |
| **Fault tolerance** | Failed truck assignments trigger automatic retry with a different truck candidate |

### Deployment

- **Platform**: DALI (Dynamic Agent Logic and Interaction), SWI-Prolog-based
- **Agent instances**: 8 agents total (1 ControlCenter, 3 SmartBins, 3 Trucks, 1 Logger)
- **Shared secret**: `city_token_2026` — all messages carry this token for authentication
- **Dashboard**: Web-based real-time monitor (Python/WebSocket bridge + HTML5 frontend)

---

## 2. Agent Roles and Virtual Organization

### 2.1 Virtual Organization Overview

The SWMS defines a hierarchical virtual organization with three functional layers:

```
┌─────────────────────────────────────────────────────┐
│              MANAGEMENT LAYER                       │
│   ControlCenter (coordinator + supervisor)          │
└────────────────────┬────────────────────────────────┘
                     │  task delegation
        ┌────────────┴────────────┐
        ▼                         ▼
┌───────────────┐       ┌───────────────────┐
│ FIELD LAYER   │       │  SENSING LAYER    │
│ Truck ×3      │       │  SmartBin ×3      │
└───────────────┘       └───────────────────┘
        │                         │
        └──────────┬──────────────┘
                   ▼
          ┌─────────────────┐
          │  SUPPORT LAYER  │
          │  Logger ×1      │
          └─────────────────┘
```

---

### 2.2 Role Schema: ControlCenter

| Attribute | Value |
|---|---|
| **Role name** | ControlCenter |
| **Instances** | 1 (`control_center`) |
| **Type** | Coordinator / Supervisor |
| **Liveness** | Cyclic (1 s cycle) + event-driven |

**Responsibilities**

- Receive `bin_full` alerts from SmartBins and open a new collection request
- Select an available (idle) truck candidate using round-robin/avoidance heuristic
- Dispatch `pickup_request` to the selected truck
- Escalate to `assignment` after truck acceptance
- Track the lifecycle of every in-flight request through four protocol stages:
  `awaiting_reply → awaiting_assign_ack → awaiting_completion → awaiting_reset_ack`
- Supervise all stages with TTL-based timeouts and retry on failure
- Issue `reset_bin` to the SmartBin once collection is confirmed

**Permissions**

| Permission | Target | Type |
|---|---|---|
| Send `pickup_request` | Truck | write |
| Send `assignment` | Truck | write |
| Send `reset_bin` | SmartBin | write |
| Send `log_event_in` | Logger | write |
| Read `truck_state` | Internal KB | read/write |
| Read `inflight` records | Internal KB | read/write |
| Read `request` records | Internal KB | read/write |

**Activities**

- `handle_bin_full` — routes a new or duplicate bin-full alert
- `select_truck` — picks the best idle truck, avoiding already-tried ones
- `do_dispatch` — sends pickup_request and opens the inflight record
- `do_accept` — registers truck acceptance, sends assignment, advances stage
- `do_refuse` — removes failed request, retries with next truck
- `do_ack` — confirms assignment acknowledgement, advances stage
- `do_collect_complete` — closes inflight, sends reset to bin
- `do_reset_ack` — fully closes the request lifecycle
- `process_timeouts` (cyclic) — decrements TTL counters, fires retry on expiry

---

### 2.3 Role Schema: Truck

| Attribute | Value |
|---|---|
| **Role name** | Truck |
| **Instances** | 3 (`truck1`, `truck2`, `truck3`) |
| **Type** | Executor / Field agent |
| **Liveness** | Cyclic (1 s monitor tick) + event-driven |

**Responsibilities**

- Evaluate incoming `pickup_request` against current state (idle / busy)
- Accept or refuse pickup requests
- Upon assignment: move to the bin (simulated via `move_time` ticks), then collect waste (`collect_time` ticks)
- Report `collection_complete` to ControlCenter
- Handle duplicate assignment messages idempotently

**Permissions**

| Permission | Target | Type |
|---|---|---|
| Send `job_accept` | ControlCenter | write |
| Send `job_refuse` | ControlCenter | write |
| Send `assignment_ack` | ControlCenter | write |
| Send `collection_complete` | ControlCenter | write |
| Read/write `truck_state` | Internal KB | read/write |
| Read `current_job` | Internal KB | read/write |

**Activities**

- `handle_pickup_request` — guards idle/busy state, triggers accept or refuse
- `accept_request` — sends `job_accept` to ControlCenter
- `refuse_request` — sends `job_refuse` to ControlCenter
- `handle_assignment` — idempotency check, then starts move phase
- `start_move` — sets state to `moving`, arms move counter
- `tick_move_phase` — decrements move counter; on zero transitions to `collecting`
- `tick_collect_phase` — decrements collect counter; on zero fires `success`
- `success` — sends `collection_complete`, cleans up local state, sets idle
- `assignment_timeout` — self-timeout when no assignment arrives after accepting

---

### 2.4 Role Schema: SmartBin

| Attribute | Value |
|---|---|
| **Role name** | SmartBin |
| **Instances** | 3 (`smart_bin1`, `smart_bin2`, `smart_bin3`) |
| **Type** | Sensor / Actuator |
| **Liveness** | Cyclic (heartbeat tick, period = `deltaT` × 1 s) |

**Responsibilities**

- Periodically increment fill level by `fill_step` (20%) up to `max_capacity` (100%)
- On reaching capacity: transition to `waiting` state and notify ControlCenter with `bin_full`
- If notification goes unanswered: periodically retry `bin_full` alert
- On `reset_bin` from ControlCenter: zero the fill level, return to `idle`, acknowledge with `reset_ack`

**Permissions**

| Permission | Target | Type |
|---|---|---|
| Send `bin_full` | ControlCenter | write |
| Send `reset_ack` | ControlCenter | write |
| Send `log_in` | Logger | write |
| Read/write `bin_level` | Internal KB | read/write |
| Read/write `bin_state` | Internal KB | read/write |

**Activities**

- `maybe_fill` — triggers level increment when idle
- `increase_level` — increments `bin_level` by fill_step; fires `full_trigger` on reaching capacity
- `full_trigger` — sets state to `waiting`, sends `bin_full` alert
- `retry_collection` — resends `bin_full` if still in `waiting` state on next tick
- `handle_reset` — idempotency-guarded reset handler
- `apply_reset_now` — zeroes level, sets state to `idle`

---

### 2.5 Role Schema: Logger

| Attribute | Value |
|---|---|
| **Role name** | Logger |
| **Instances** | 1 (`logger`) |
| **Type** | Support / Monitor |
| **Liveness** | Event-driven only |

**Responsibilities**

- Accept log messages from any agent via `log_in` and `log_event_in`
- Persist log entries as timestamped facts in the knowledge base
- Deduplicate near-identical messages within a 1.2 s sliding window
- Print formatted output to console

**Permissions**

| Permission | Target | Type |
|---|---|---|
| Receive `log_in` | Any agent | read |
| Receive `log_event_in` | Any agent | read |
| Write `log_store` facts | Internal KB | write |

---

## 3. Interaction Model

### 3.1 Collection Protocol (Happy Path)

The primary interaction protocol governs the full lifecycle of a single waste collection request.

```
SmartBin          ControlCenter           Truck            SmartBin
    │                   │                   │                  │
    │──bin_full(B,Tok)──▶│                  │                  │
    │                   │                   │                  │
    │                   │──pickup_request(B,ReqId,Tok)──▶│     │
    │                   │                   │                  │
    │                   │◀──job_accept(Tr,B,ReqId,Tok)───│     │
    │                   │                   │                  │
    │                   │──assignment(B,ReqId,Tok)───────▶│    │
    │                   │                   │                  │
    │                   │◀─assignment_ack(Tr,B,ReqId,Tok)─│    │
    │                   │                   │                  │
    │                   │      [Truck moves to bin, collects]  │
    │                   │                   │                  │
    │                   │◀─collection_complete(B,ReqId,Tok)─│  │
    │                   │                   │                  │
    │                   │──────────reset_bin(B,ReqId,Tok)──────▶│
    │                   │                   │                  │
    │                   │◀──────────reset_ack(B,ReqId,Tok)─────│
    │                   │                   │                  │
    ║ [cycle closed]    ║                   ║                  ║
```

### 3.2 Refuse & Retry Protocol

When a truck is busy, the control center retries with the next available truck.

```
ControlCenter           Truck-A            Truck-B
    │                     │                  │
    │──pickup_request──▶  │                  │
    │                     │                  │
    │◀──job_refuse──────  │                  │
    │                     │                  │
    │──pickup_request────────────────────▶   │
    │                     │                  │
    │◀──job_accept──────────────────────── │  │
    │                     │                  │
    │ (continues with assignment protocol)   │
```

### 3.3 Timeout & Retry Protocol

Each inflight stage is guarded by a TTL counter decremented on each ControlCenter cycle:

| Stage | TTL parameter | Default | On expiry |
|---|---|---|---|
| `awaiting_reply` | `reply_ttl` | 6 cycles | Re-dispatch to another truck |
| `awaiting_assign_ack` | `assign_ack_ttl` | 6 cycles | Resend `assignment` |
| `awaiting_completion` | `completion_ttl` | 10 cycles | Log & close (truck lost) |
| `awaiting_reset_ack` | `reset_ack_ttl` | 3 cycles | Resend `reset_bin` |

### 3.4 Logging Protocol

Any agent may emit log entries directly to the Logger at any time (fire-and-forget):

```
AnyAgent                Logger
   │                      │
   │──log_in(Level, Msg, Sender)──▶│
   │                      │  (dedup check)
   │                      │  (persist + print)
```

---

## 4. Event Table

> **Reading guide** — Events are grouped by origin and role:
> - **External Events** are messages received from other agents — these are the primary protocol drivers.
> - **Core Lifecycle Events** are the internal transitions that implement the protocol logic.
> - **Timeout & Recovery Events** implement TTL-based fault tolerance.
> - **Cyclic & Init Events** are heartbeat and startup mechanics.

---

### 4.1 ControlCenter — Event Table

**External Events** *(received from other agents — primary protocol drivers)*

| Event | Source | Trigger | Description |
|---|---|---|---|
| `bin_full(Bin, Token)` | SmartBin | Fill level = 100% | Bin requests collection; opens new request or resends assignment |
| `job_accept(Truck, Bin, ReqId, Token)` | Truck | Truck accepts pickup | Triggers `assignment` dispatch; truck marked busy |
| `job_refuse(Truck, Bin, ReqId, Token)` | Truck | Truck refuses pickup | Marks truck as tried; retries with next available truck |
| `assignment_ack(Truck, Bin, ReqId, Token)` | Truck | Truck confirms assignment | Advances inflight stage to `awaiting_completion` |
| `collection_complete(Bin, ReqId, Token)` | Truck | Truck finishes collection | Closes inflight record; sends `reset_bin` to SmartBin |
| `reset_ack(Bin, ReqId, Token)` | SmartBin | Bin confirms reset | Fully closes the request lifecycle |

**Core Lifecycle Events** *(internal protocol transitions)*

| Event | Source | Trigger | Description |
|---|---|---|---|
| `handle_bin_full_new(Bin)` | Internal | No open request for Bin | Opens a new collection request; generates `ReqId` |
| `handle_bin_full_retry(Bin, ReqId, T)` | Internal | Request already open | Resends `assignment` to the currently assigned truck |
| `dispatch_bin_full(Bin, ReqId, T)` | Internal | After truck selected | Opens inflight record; sends `pickup_request` to truck |
| `do_accept(Truck, Bin, ReqId)` | Internal | After `job_accept` | Sets truck busy; sends `assignment` |
| `do_refuse(Truck, Bin, ReqId)` | Internal | After `job_refuse` | Records tried truck; selects next idle truck |
| `do_ack(Truck, Bin, ReqId, R)` | Internal | After `assignment_ack` | Advances inflight stage |
| `do_collect_complete(Bin, ReqId, Truck)` | Internal | After `collection_complete` | Sends `reset_bin`; marks request complete |
| `do_reset_ack(Bin, ReqId, Truck)` | Internal | After `reset_ack` | Removes inflight record; request fully closed |

**Timeout & Recovery Events** *(TTL-based fault tolerance)*

| Event | Source | Trigger | Description |
|---|---|---|---|
| `process_timeouts` | Internal (cyclic) | Every cycle | Scans all inflight records; decrements TTL counters |
| `reply_timeout_step(ReqId, Bin, T)` | Internal | TTL = 0 at `awaiting_reply` | Re-dispatches pickup request to the next available truck |
| `assign_ack_timeout_step(ReqId, Bin, T, R)` | Internal | TTL = 0 at `awaiting_assign_ack` | Resends `assignment` to the selected truck |
| `completion_timeout_step(ReqId, Bin, T)` | Internal | TTL = 0 at `awaiting_completion` | Logs and closes the stale request (truck considered lost) |
| `reset_ack_timeout_step(ReqId, Bin, T)` | Internal | TTL = 0 at `awaiting_reset_ack` | Resends `reset_bin` to the SmartBin |

**Cyclic & Initialization Events**

| Event | Source | Trigger | Description |
|---|---|---|---|
| `start` | Internal | System init | Initializes KB, truck states, and request sequence counter |
| `monitor(dummy)` | Internal | Every tick | Heartbeat; triggers `cycle` if interval elapsed |
| `cycle` | Internal | Per cycle | Fires `process_timeouts`; advances cyclic supervision logic |

---

### 4.2 Truck — Event Table

**External Events** *(received from ControlCenter — primary protocol drivers)*

| Event | Source | Trigger | Description |
|---|---|---|---|
| `pickup_request(Bin, ReqId, Token)` | ControlCenter | CC assigns a collection job | Guards on truck state; routes to accept or refuse |
| `assignment(Bin, ReqId, Token)` | ControlCenter | CC confirms the assignment | Idempotency check; starts the move phase |

**Core Lifecycle Events** *(internal protocol transitions)*

| Event | Source | Trigger | Description |
|---|---|---|---|
| `accept_request(Bin, ReqId)` | Internal | Truck is idle | Sends `job_accept` to ControlCenter |
| `refuse_request(Bin, ReqId)` | Internal | Truck is busy | Sends `job_refuse` to ControlCenter |
| `handle_assignment(Bin, ReqId)` | Internal | After `assignment` received | Idempotency check; triggers `start_move` |
| `start_move(Bin, ReqId)` | Internal | Assignment accepted | Arms move counter; sets state to `moving` |
| `tick_move_phase` | Internal (cyclic) | Each monitor tick while `moving` | Decrements move counter; transitions to `collecting` on zero |
| `tick_collect_phase` | Internal (cyclic) | Each monitor tick while `collecting` | Decrements collect counter; fires `success` on zero |
| `success(Bin, ReqId)` | Internal | Collection done | Sends `collection_complete` to ControlCenter; returns to `idle` |
| `assignment_timeout` | Internal | Assignment wait limit expired | Self-refuses if no assignment arrives after accepting |
| `cleanup` | Internal | After timeout or reset | Resets all counters; sets truck to `idle` |

**Cyclic & Initialization Events**

| Event | Source | Trigger | Description |
|---|---|---|---|
| `start` | Internal | System init | Initializes local state; sets truck to `idle` |
| `monitor(dummy)` | Internal | Every tick | Heartbeat; fires `monitor_tick` if interval elapsed |
| `monitor_tick` | Internal | Per tick | Dispatches all tick sub-events (move, collect, assignment wait) |

---

### 4.3 SmartBin — Event Table

**External Events** *(received from ControlCenter)*

| Event | Source | Trigger | Description |
|---|---|---|---|
| `reset_bin(Bin, ReqId, Token)` | ControlCenter | CC orders reset after collection | Triggers idempotency-guarded reset handler |

**Core Lifecycle Events** *(internal fill and alert transitions)*

| Event | Source | Trigger | Description |
|---|---|---|---|
| `maybe_fill` | Internal | State = `idle` on tick | Triggers level increment |
| `increase_level` | Internal | Bin level < 100% | Increments `bin_level` by `fill_step` (20%) |
| `full_trigger` | Internal | Level reaches 100% | Sets state to `waiting`; sends `bin_full` to ControlCenter |
| `retry_collection` | Internal (cyclic) | State = `waiting` on tick | Resends `bin_full` if no reset has arrived |
| `handle_reset(ReqId)` | Internal | After `reset_bin` received | Idempotency-guarded reset dispatcher |
| `apply_reset_now` | Internal | First reset for this `ReqId` | Zeroes level; sets state to `idle`; sends `reset_ack` |

**Cyclic & Initialization Events**

| Event | Source | Trigger | Description |
|---|---|---|---|
| `start` | Internal | System init | Initializes `level = 0`, `state = idle`, heartbeat counter |
| `monitor(dummy)` | Internal | Every tick | Heartbeat; fires `monitor_tick` if interval elapsed |
| `monitor_tick` | Internal | Per `deltaT` seconds | Routes to `maybe_fill` (idle) or `retry_collection` (waiting) |

---

### 4.4 Logger — Event Table

**External Events** *(received from any agent — primary entry points)*

| Event | Source | Trigger | Description |
|---|---|---|---|
| `log_in(Level, Event, Sender)` | Any agent | Any agent logs text | Dedup-checked; persists and prints a free-text log entry |
| `log_event_in(Level, Name, ReqId, Bin, Truck, Note, Sender)` | ControlCenter | Structured lifecycle event | Dedup-checked; persists and prints a structured event entry |

**Internal Events**

| Event | Source | Trigger | Description |
|---|---|---|---|
| `should_print(Key, Level, Sender, Msg)` | Internal | After every log event | Deduplication gate; suppresses if same key seen within 1.2 s |
| `print_log(Level, Sender, Msg)` | Internal | After dedup pass | Formats and writes the log line to stdout |
| `start` | Internal | System init | Clears log store and dedup cache |
| `monitor(dummy)` | Internal | Heartbeat | Fires `start` if not yet initialized |

---

## 5. Action Table

> **Reading guide** — Actions are grouped by type:
> - **Outgoing Messages** are the primary inter-agent communication actions.
> - **State Management** covers all knowledge-base read/write operations.
> - **Utilities** covers helper predicates (timestamps, formatting, logging helpers).

---

### 5.1 ControlCenter — Action Table

**Outgoing Messages** *(inter-agent communication)*

| Action | Sent To | Message Emitted |
|---|---|---|
| `send_pickup_requestA(Truck, Bin, ReqId, Token)` | Truck | `pickup_request(Bin, ReqId, Token)` |
| `send_assignmentA(Truck, Bin, ReqId, Token)` | Truck | `assignment(Bin, ReqId, Token)` |
| `send_resetA(Bin, ReqId, Token)` | SmartBin | `reset_bin(Bin, ReqId, Token)` |
| `send_logA(Level, Event, Sender)` | Logger | Free-text log entry |
| `send_log_eventA(Level, Name, ReqId, Bin, Truck, Note)` | Logger | Structured lifecycle event |

**State Management** *(knowledge base operations)*

| Action | Effect |
|---|---|
| `set_truck_idleA(Truck)` | Retracts and reasserts `truck_state(Truck, idle)` |
| `set_truck_busyA(Truck)` | Retracts and reasserts `truck_state(Truck, busy)` |
| `open_inflightA(ReqId, Bin, T, Stage, Ttl)` | Creates a new inflight record for the given request stage |
| `close_inflightA(ReqId, Bin, T)` | Removes inflight record on stage completion or failure |
| `mark_repliedA(Req, Truck, Result)` | Records truck reply (accept/refuse) to prevent duplicate processing |
| `assert_triedA(Bin, Truck)` | Marks a truck as already tried for this bin request |
| `clear_tried_binA(Bin)` | Clears tried-truck history for a bin on successful completion |
| `assert_handled_binA(Bin)` | Prevents duplicate handling of the same `bin_full` alert |
| `complete_reqA(ReqId)` | Marks a request as fully completed |
| `generate_req_idA(ReqId)` | Atomically increments and returns the request sequence counter |
| `ensure_runtime_stateA` | Lazy-initialises `req_seq` and `truck_state` facts if absent |

**Utilities**

| Action | Effect |
|---|---|
| `timestampA(Now)` | Reads current walltime in milliseconds |
| `display_binA(Bin, Bp)` | Converts `smart_binN` to display form `smartbinN` |
| `log_cc_startA` | Prints control center startup banner |
| `log_bin_full_newA(Bp)` | Prints `stage=bin_full_received` message |
| `log_pickup_sentA(ReqId, T, Bp)` | Prints `stage=pickup_request_sent` message |
| `log_pickup_acceptedA(ReqId, Truck, Bp)` | Prints `stage=pickup_accepted` message |
| `log_pickup_refusedA(ReqId, Truck, Bp)` | Prints `stage=pickup_refused` message |
| `log_retry_assignA(ReqId, T, Bp)` | Prints `stage=retry_assignment` message |
| `log_assign_ackedA(ReqId, Truck, Bp)` | Prints `stage=assignment_acked` message |
| `log_collection_completeA(ReqId, Truck, Bp)` | Prints `stage=collection_complete` message |
| `log_reset_ackedA(ReqId, Truck, Bp)` | Prints `stage=reset_acked` message |

---

### 5.2 Truck — Action Table

**Outgoing Messages** *(inter-agent communication)*

| Action | Sent To | Message Emitted |
|---|---|---|
| `send_acceptA(Bin, ReqId, Token)` | ControlCenter | `job_accept(Truck, Bin, ReqId, Token)` |
| `send_refuseA(Bin, ReqId, Token)` | ControlCenter | `job_refuse(Truck, Bin, ReqId, Token)` |
| `send_assignment_ackA(Bin, ReqId, Token)` | ControlCenter | `assignment_ack(Truck, Bin, ReqId, Token)` |
| `send_completionA(Bin, ReqId, Token)` | ControlCenter | `collection_complete(Bin, ReqId, Token)` |

**State Management** *(knowledge base operations)*

| Action | Effect |
|---|---|
| `set_idleA` | Retracts all `truck_state(_)` facts; asserts `truck_state(idle)` |
| `set_stateA(State)` | Transitions truck to given state: `idle` / `waiting_assignment` / `moving` / `collecting` |

**Utilities**

| Action | Effect |
|---|---|
| `timestampA(Now)` | Reads current walltime in milliseconds |
| `display_binA(Bin, Bp)` | Converts `smart_binN` to display form `smartbinN` |
| `log_startedA(Truck)` | Prints truck startup banner |
| `log_pickup_acceptA(Truck, Bp)` | Prints `stage=pickup_accept` message |
| `log_pickup_refuseA(Truck, Bp)` | Prints `stage=pickup_refuse` message |
| `log_move_toA(Truck, Bp, M)` | Prints `stage=move_to_bin` with move-time ETA |
| `log_collect_wasteA(Truck, Bp, Ct)` | Prints `stage=collect_waste` with collect-time ETA |
| `log_report_completeA(Truck, Bp)` | Prints `stage=report_completion` message |

---

### 5.3 SmartBin — Action Table

**Outgoing Messages** *(inter-agent communication)*

| Action | Sent To | Message Emitted |
|---|---|---|
| `send_full_alertA(BinId, Token)` | ControlCenter | `bin_full(BinId, Token)` |
| `send_full_alert_if_readyA(BinId, Token)` | ControlCenter | `bin_full(BinId, Token)` — only if CC is reachable (non-blocking) |
| `send_reset_ackA(BinId, ReqId, Token)` | ControlCenter | `reset_ack(BinId, ReqId, Token)` |
| `send_logA(Level, Event, Sender)` | Logger | Free-text log entry |
| `send_level_logA(BinId, NL)` | Logger | Formatted fill-level update entry |

**State Management** *(knowledge base operations)*

| Action | Effect |
|---|---|
| `set_bin_stateA(State)` | Transitions bin state: `idle` ↔ `waiting` |
| `update_levelA(NL)` | Replaces current `bin_level` fact with new level value |

**Utilities**

| Action | Effect |
|---|---|
| `timestampA(Now)` | Reads current walltime in milliseconds |
| `display_binA(BinId, Bp)` | Converts `smart_binN` to display form `smartbinN` |
| `log_bin_startedA(Bp)` | Prints bin startup banner |
| `log_bin_readyA(Bp)` | Prints bin ready message |
| `log_level_pctA(Bp, NL)` | Prints current fill level percentage |
| `log_bin_fullA(Bp, L)` | Prints `stage=full` with current level and notify target |
| `log_bin_resetA(Bp)` | Prints `stage=reset level=0%` message |

---

### 5.4 Logger — Action Table

**State Management** *(knowledge base operations)*

| Action | Effect |
|---|---|
| `assert(log_store(T, Sender, Event, Level))` | Persists a timestamped log entry in the knowledge base |
| `assert(recent_log(Key, Now))` | Records the timestamp of the last printed occurrence of a log key |
| `retractall(log_store/4)` | Clears the entire log store on restart |
| `retractall(recent_log/2)` | Clears the deduplication cache on restart |

**Output**

| Action | Effect |
|---|---|
| `format('[logger] ~w  ~w~n', [Lvl, Msg])` | Writes a formatted log line to console stdout |

---

## Summary: Agent Communication Matrix

| Sender → Receiver | Message | Protocol stage |
|---|---|---|
| SmartBin → ControlCenter | `bin_full(Bin, Token)` | Alert |
| ControlCenter → Truck | `pickup_request(Bin, ReqId, Token)` | Request |
| Truck → ControlCenter | `job_accept(Truck, Bin, ReqId, Token)` | Acceptance |
| Truck → ControlCenter | `job_refuse(Truck, Bin, ReqId, Token)` | Refusal |
| ControlCenter → Truck | `assignment(Bin, ReqId, Token)` | Confirmation |
| Truck → ControlCenter | `assignment_ack(Truck, Bin, ReqId, Token)` | Acknowledgement |
| Truck → ControlCenter | `collection_complete(Bin, ReqId, Token)` | Completion |
| ControlCenter → SmartBin | `reset_bin(Bin, ReqId, Token)` | Reset order |
| SmartBin → ControlCenter | `reset_ack(Bin, ReqId, Token)` | Reset confirmation |
| Any → Logger | `log_in(Level, Msg, Sender)` | Logging |
| ControlCenter → Logger | `log_event_in(Level, Name, ReqId, Bin, Truck, Note, Sender)` | Structured logging |
