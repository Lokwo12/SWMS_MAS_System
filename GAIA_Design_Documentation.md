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

### 4.1 ControlCenter — Event Table

| Event | Source | Trigger | Description |
|---|---|---|---|
| `start` | Internal | System init | Initializes KB, truck states, request counter |
| `monitor(dummy)` | Internal (cyclic) | Every tick | Heartbeat; triggers cycle if interval elapsed |
| `cycle` | Internal | Per cycle | Fires `process_timeouts` and `cycle_completed` |
| `bin_full(Bin, Token)` | SmartBin | Fill level = 100% | Alerts that a bin requires collection |
| `handle_bin_full(Bin)` | Internal | On `bin_full` receipt | Routes to new-request or retry handler |
| `route_bin_full(Bin)` | Internal | After `handle_bin_full` | Selects new vs. retry path |
| `handle_bin_full_new(Bin)` | Internal | No open request for Bin | Opens a new collection request |
| `handle_bin_full_retry(Bin,ReqId,T)` | Internal | Request already open | Resends `assignment` to the current truck |
| `select_truck(ReqId, Bin)` | Internal | After new request opened | Selects the best idle truck candidate |
| `dispatch_bin_full(Bin,ReqId,T)` | Internal | After truck selected | Opens inflight record, sends `pickup_request` |
| `job_accept(Truck,Bin,ReqId,Token)` | Truck | Truck accepts pickup | Triggers assignment dispatch |
| `do_accept(Truck,Bin,ReqId)` | Internal | After `job_accept` | Sets truck busy, sends `assignment` |
| `job_refuse(Truck,Bin,ReqId,Token)` | Truck | Truck refuses pickup | Triggers retry with another truck |
| `do_refuse(Truck,Bin,ReqId)` | Internal | After `job_refuse` | Marks truck tried, selects next truck |
| `assignment_ack(Truck,Bin,ReqId,Token)` | Truck | Truck confirms assignment | Advances stage to `awaiting_completion` |
| `do_ack(Truck,Bin,ReqId,R)` | Internal | After `assignment_ack` | Updates inflight stage |
| `collection_complete(Bin,ReqId,Token)` | Truck | Truck finishes collection | Triggers bin reset |
| `do_collect_complete(Bin,ReqId,Truck)` | Internal | After `collection_complete` | Sends `reset_bin`, marks request complete |
| `reset_ack(Bin,ReqId,Token)` | SmartBin | Bin confirms reset | Closes the full request lifecycle |
| `do_reset_ack(Bin,ReqId,Truck)` | Internal | After `reset_ack` | Closes inflight record |
| `process_timeouts` | Internal | Per cycle | Scans all inflight records for TTL expiry |
| `timeout_step(ReqId,Bin,T,Stage,Ttl,R)` | Internal | Per inflight record | Decrements TTL or fires timeout handler |
| `reply_timeout_step(ReqId,Bin,T)` | Internal | TTL=0 at `awaiting_reply` | Re-dispatches to next truck |
| `assign_ack_timeout_step(ReqId,Bin,T,R)` | Internal | TTL=0 at `awaiting_assign_ack` | Resends `assignment` |
| `completion_timeout_step(ReqId,Bin,T)` | Internal | TTL=0 at `awaiting_completion` | Closes stale request |
| `reset_ack_timeout_step(ReqId,Bin,T)` | Internal | TTL=0 at `awaiting_reset_ack` | Resends `reset_bin` |
| `truck_idle(Truck)` | Internal | Truck freed | Updates truck state to idle |
| `truck_busy(Truck)` | Internal | Truck assigned | Updates truck state to busy |
| `watchdog_check` | Internal | Cyclic | Health monitoring |

---

### 4.2 Truck — Event Table

| Event | Source | Trigger | Description |
|---|---|---|---|
| `start` | Internal | System init | Initializes local state, sets idle |
| `monitor(dummy)` | Internal (cyclic) | Every tick | Heartbeat; fires `monitor_tick` if interval elapsed |
| `monitor_tick` | Internal | Per tick | Triggers all tick sub-events |
| `pickup_request(Bin,ReqId,Token)` | ControlCenter | CC sends pickup_request | External message received |
| `handle_pickup_request(Bin,ReqId)` | Internal | After `pickup_request` | Guards on truck state, routes to accept/refuse |
| `accept_request(Bin,ReqId)` | Internal | Truck is idle | Sends `job_accept` to ControlCenter |
| `refuse_request(Bin,ReqId)` | Internal | Truck is busy | Sends `job_refuse` to ControlCenter |
| `assignment(Bin,ReqId,Token)` | ControlCenter | CC confirms assignment | External message received |
| `handle_assignment(Bin,ReqId)` | Internal | After `assignment` | Idempotency check, starts move |
| `start_move(Bin,ReqId)` | Internal | Assignment accepted | Arms move counter, sets state `moving` |
| `tick_status_counter` | Internal | Per monitor tick | Periodic status reporting |
| `tick_assignment_wait` | Internal | Per monitor tick | Counts down assignment wait window |
| `tick_move_phase` | Internal | Per monitor tick | Counts down move time; on zero → collecting |
| `tick_collect_phase` | Internal | Per monitor tick | Counts down collect time; on zero → success |
| `success(Bin,ReqId)` | Internal | Collection done | Sends `collection_complete`, returns to idle |
| `do_refuse(Bin,ReqId)` | Internal | Refuse path | Sends `job_refuse` to ControlCenter |
| `assignment_timeout` | Internal | Assignment wait limit expired | Self-refuses if assignment never arrives |
| `cleanup` | Internal | After timeout | Resets all counters, sets idle |
| `status_check` | Internal | Cyclic | Logs current status |

---

### 4.3 SmartBin — Event Table

| Event | Source | Trigger | Description |
|---|---|---|---|
| `start` | Internal | System init | Initializes level=0, state=idle, heartbeat counter |
| `monitor(dummy)` | Internal (cyclic) | Every tick | Heartbeat; fires `monitor_tick` if interval elapsed |
| `monitor_tick` | Internal | Per deltaT seconds | Fires `tick` |
| `tick` | Internal | Per heartbeat | Dispatches `maybe_fill` or `retry_collection` based on state |
| `maybe_fill` | Internal | State = idle | Triggers level increment |
| `increase_level` | Internal | Bin level < 100% | Increments level by fill_step (20%) |
| `full_trigger` | Internal | Level reaches 100% | Sets state to `waiting`, sends `bin_full` alert |
| `retry_collection` | Internal | State = waiting on tick | Resends `bin_full` to ControlCenter |
| `reset_bin(Bin,ReqId,Token)` | ControlCenter | CC orders reset after collection | External message received |
| `handle_reset(ReqId)` | Internal | After `reset_bin` | Idempotency-guarded reset dispatcher |
| `apply_reset_now` | Internal | First reset for this ReqId | Zeroes level, sets state to `idle`, sends `reset_ack` |

---

### 4.4 Logger — Event Table

| Event | Source | Trigger | Description |
|---|---|---|---|
| `start` | Internal | System init | Clears log store and dedup cache |
| `monitor(dummy)` | Internal | Heartbeat | Fires `start` if not yet started |
| `log_in(Level,Event,Sender)` | Any agent | Any agent logs text | Persists and prints a free-text log entry |
| `log_event_in(Level,Name,ReqId,Bin,Truck,Note,Sender)` | ControlCenter | Structured lifecycle event | Persists and prints a structured event log entry |
| `should_print(Key,Level,Sender,Msg)` | Internal | After log_in / log_event_in | Deduplication check; suppresses if same key seen within 1.2 s |
| `print_log(Level,Sender,Msg)` | Internal | After dedup pass | Formats and writes log line to stdout |

---

## 5. Action Table

### 5.1 ControlCenter — Action Table

| Action | Type | Effect |
|---|---|---|
| `send_pickup_requestA(Truck,Bin,ReqId,Token)` | Message | Sends `pickup_request(Bin,ReqId,Token)` to Truck |
| `send_assignmentA(Truck,Bin,ReqId,Token)` | Message | Sends `assignment(Bin,ReqId,Token)` to Truck |
| `send_resetA(Bin,ReqId,Token)` | Message | Sends `reset_bin(Bin,ReqId,Token)` to SmartBin |
| `send_logA(Level,Event,Sender)` | Message | Sends free-text log entry to Logger |
| `send_log_eventA(Level,Name,ReqId,Bin,Truck,Note)` | Message | Sends structured lifecycle event to Logger |
| `set_truck_idleA(Truck)` | State | Retracts and reasserts `truck_state(Truck, idle)` |
| `set_truck_busyA(Truck)` | State | Retracts and reasserts `truck_state(Truck, busy)` |
| `open_inflightA(ReqId,Bin,T,Stage,Ttl)` | State | Creates new inflight record for a request stage |
| `close_inflightA(ReqId,Bin,T)` | State | Removes inflight record when stage completes or fails |
| `mark_repliedA(Req,Truck,Result)` | State | Records truck reply (accept/refuse) to prevent duplicates |
| `assert_triedA(Bin,Truck)` | State | Marks a truck as already tried for a bin request |
| `clear_tried_binA(Bin)` | State | Clears tried-truck history for a bin (on success) |
| `assert_handled_binA(Bin)` | State | Prevents duplicate handling of same bin_full alert |
| `complete_reqA(ReqId)` | State | Marks a request as completed |
| `generate_req_idA(ReqId)` | State | Atomically increments and returns the request sequence counter |
| `ensure_runtime_stateA` | State | Lazy-initialises req_seq and truck_state if absent |
| `timestampA(Now)` | Utility | Reads current walltime in ms |
| `display_binA(Bin,Bp)` | Utility | Converts `smart_binN` to display form `smartbinN` |
| `log_cc_startA` | Log | Prints control center startup message |
| `log_bin_full_newA(Bp)` | Log | Prints bin_full_received stage message |
| `log_retry_assignA(ReqId,T,Bp)` | Log | Prints retry_assignment stage message |
| `log_pickup_acceptedA(ReqId,Truck,Bp)` | Log | Prints pickup_accepted stage message |
| `log_pickup_refusedA(ReqId,Truck,Bp)` | Log | Prints pickup_refused stage message |
| `log_assign_ackedA(ReqId,Truck,Bp)` | Log | Prints assignment_acked stage message |
| `log_collection_completeA(ReqId,Truck,Bp)` | Log | Prints collection_complete stage message |
| `log_reset_ackedA(ReqId,Truck,Bp)` | Log | Prints reset_acked stage message |
| `log_pickup_sentA(ReqId,T,Bp)` | Log | Prints pickup_request_sent stage message |

---

### 5.2 Truck — Action Table

| Action | Type | Effect |
|---|---|---|
| `send_acceptA(Bin,ReqId,Token)` | Message | Sends `job_accept(Truck,Bin,ReqId,Token)` to ControlCenter |
| `send_refuseA(Bin,ReqId,Token)` | Message | Sends `job_refuse(Truck,Bin,ReqId,Token)` to ControlCenter |
| `send_assignment_ackA(Bin,ReqId,Token)` | Message | Sends `assignment_ack(Truck,Bin,ReqId,Token)` to ControlCenter |
| `send_completionA(Bin,ReqId,Token)` | Message | Sends `collection_complete(Bin,ReqId,Token)` to ControlCenter |
| `set_idleA` | State | Retracts all `truck_state(_)` facts and asserts `truck_state(idle)` |
| `set_stateA(State)` | State | Transitions truck state to any given state (`idle`, `waiting_assignment`, `moving`, `collecting`) |
| `timestampA(Now)` | Utility | Reads current walltime in ms |
| `display_binA(Bin,Bp)` | Utility | Converts `smart_binN` to display form `smartbinN` |
| `log_pickup_acceptA(Truck,Bp)` | Log | Prints `stage=pickup_accept` message |
| `log_pickup_refuseA(Truck,Bp)` | Log | Prints `stage=pickup_refuse` message |
| `log_move_toA(Truck,Bp,M)` | Log | Prints `stage=move_to_bin` with ETA |
| `log_collect_wasteA(Truck,Bp,Ct)` | Log | Prints `stage=collect_waste` with ETA |
| `log_report_completeA(Truck,Bp)` | Log | Prints `stage=report_completion` message |
| `log_startedA(Truck)` | Log | Prints truck startup message |

---

### 5.3 SmartBin — Action Table

| Action | Type | Effect |
|---|---|---|
| `send_full_alertA(BinId,Token)` | Message | Sends `bin_full(BinId,Token)` to ControlCenter |
| `send_full_alert_if_readyA(BinId,Token)` | Message | Sends `bin_full` only if ControlCenter is active (non-blocking check) |
| `send_reset_ackA(BinId,ReqId,Token)` | Message | Sends `reset_ack(BinId,ReqId,Token)` to ControlCenter |
| `send_logA(Level,Event,Sender)` | Message | Sends free-text log entry to Logger |
| `send_level_logA(BinId,NL)` | Message | Sends formatted level-update log to Logger |
| `set_bin_stateA(State)` | State | Transitions bin state (`idle` / `waiting`) |
| `update_levelA(NL)` | State | Replaces current `bin_level` fact with new level value |
| `timestampA(Now)` | Utility | Reads current walltime in ms |
| `display_binA(BinId,Bp)` | Utility | Converts `smart_binN` to display form `smartbinN` |
| `log_bin_startedA(Bp)` | Log | Prints bin startup message |
| `log_bin_readyA(Bp)` | Log | Prints bin ready message |
| `log_level_pctA(Bp,NL)` | Log | Prints current fill level percentage |
| `log_bin_fullA(Bp,L)` | Log | Prints `stage=full` with current level and notify target |
| `log_bin_resetA(Bp)` | Log | Prints `stage=reset level=0%` message |

---

### 5.4 Logger — Action Table

| Action | Type | Effect |
|---|---|---|
| `assert(log_store(T,Sender,Event,Level))` | State | Persists a timestamped log entry in the knowledge base |
| `retractall(log_store/4)` | State | Clears entire log store on restart |
| `assert(recent_log(Key,Now))` | State | Records timestamp of last printed occurrence of a log key |
| `retractall(recent_log/2)` | State | Clears deduplication cache on restart |
| `format('[logger] ~w  ~w~n', [Lvl, Msg])` | Output | Writes formatted log line to console stdout |

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
