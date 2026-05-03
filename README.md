# SWMS — Smart Waste Management System

> A fully autonomous Multi-Agent System for urban waste collection, built on the **DALI** logic agent platform (SICStus Prolog).

---

# Overview

**SWMS** is a research-grade Multi-Agent System (MAS) that simulates and automates the complete lifecycle of urban waste collection. The system is composed of eight cooperative autonomous agents — smart bins, collection trucks, a central coordinator, and a logger — each running as an independent DALI agent with its own reactive and proactive logic.

When a smart bin reaches maximum capacity, the system automatically:

1. Detects the fill event and opens a tracked collection request
2. Selects the best available truck through a fault-tolerant dispatch protocol
3. Supervises the truck's movement and collection phases using TTL-based timeout monitoring
4. Resets the bin to operational state once collection is confirmed

The entire workflow executes autonomously without human intervention and is resilient to:

- Truck refusals
- Delayed acknowledgements
- Lost messages
- Assignment timeouts
- Collection failures

These fault-tolerance behaviours are implemented directly inside the DALI agent logic through retries, escalation rules, and supervision cycles.

---

<<<<<<< HEAD
## 1. System Objective

The **Smart Waste Management System (SWMS)** is a Multi-Agent System (MAS) built on the DALI agent platform. Its objective is to automate the urban waste collection process through the coordinated cooperation of autonomous agents.

## 2. Agent Roles and Virtual Organization

### 2.1 Virtual Organization Overview

The SWMS defines a hierarchical virtual organization with three functional layers:
## Architecture
=======
# 1. System Objective
>>>>>>> 348004b (readme update)

The **Smart Waste Management System (SWMS)** is a Multi-Agent System built on the DALI agent platform.

Its objective is to automate urban waste collection through coordinated cooperation among autonomous intelligent agents capable of:

- Monitoring waste levels
- Dispatching collection resources
- Handling communication failures
- Supervising collection completion
- Maintaining structured event logging

---

# 2. Agent Roles and Virtual Organization

## 2.1 Virtual Organization Overview

The SWMS architecture is organized into three functional layers.

# Architecture

```text
┌─────────────────────────────────────────────────────┐
│                 MANAGEMENT LAYER                    │
│     ControlCenter (Coordinator / Supervisor)        │
└────────────────────┬────────────────────────────────┘
                     │
                     │ Task Delegation
                     ▼
        ┌───────────────────────────────┐
        │                               │
        ▼                               ▼
┌──────────────────┐      ┌────────────────────────┐
│   FIELD LAYER    │      │    SENSING LAYER       │
│   Truck ×3       │      │    SmartBin ×3         │
└──────────────────┘      └────────────────────────┘
        │                               │
        └──────────────┬────────────────┘
                       ▼
             ┌────────────────────┐
             │   SUPPORT LAYER    │
             │     Logger ×1      │
             └────────────────────┘
```

---

## Agent Definitions

| Agent | Instances | Role |
|---|---|---|
| `control_center` | 1 | Coordinator and supervisor |
| `truck1`, `truck2`, `truck3` | 3 | Waste collection executors |
| `smart_bin1`, `smart_bin2`, `smart_bin3` | 3 | Smart sensing bins |
| `logger` | 1 | Centralized event logger |

---

## Communication Protocol

All inter-agent communication includes a shared authentication token:

```text
city_token_2026
```

The coordination protocol follows a structured FIPA-inspired request-response lifecycle tracked through four states:

```text
awaiting_reply
→ awaiting_assign_ack
→ awaiting_completion
→ awaiting_reset_ack
```


# 3. Collection Workflow

```mermaid
sequenceDiagram
    participant Bin as SmartBin
    participant CC as ControlCenter
    participant Truck1 as Truck_First
    participant Truck2 as Truck_Second
    participant Logger
<<<<<<< HEAD

    Note over Bin: Periodically fills up

    Bin->>Bin: increase_level()

    alt Bin becomes full

        Bin->>CC: bin_full(BinId Token)
        Bin->>Logger: log(info bin_full BinId)

        CC->>CC: generate ReqId and select idle truck

        CC->>Truck1: pickup_request(BinId ReqId Token)

        CC->>Logger: log(info pickup_request_sent ReqId BinId Truck1)

        alt Truck1 accepts

            Truck1->>CC: job_accept(Truck1 BinId ReqId Token)

            Truck1->>Logger: log(info pickup_accept BinId)

            CC->>CC: update state to awaiting_assign_ack

            CC->>Truck1: assignment(BinId ReqId Token)

            Truck1->>CC: assignment_ack(Truck1 BinId ReqId Token)

            CC->>CC: update state to awaiting_completion

            Note over Truck1: move timer

            Truck1->>Truck1: move for move_time ticks

            Note over Truck1: collect timer

            Truck1->>Truck1: collect for collect_time ticks

            Truck1->>CC: collection_complete(BinId ReqId Token)

            CC->>CC: update state to awaiting_reset_ack

            CC->>Bin: reset_bin(BinId ReqId Token)

            Bin->>Bin: reset level to 0

            Bin->>CC: reset_ack(BinId ReqId Token)

            Bin->>Logger: log(info bin_reset BinId)

            CC->>CC: close request and clear inflight

            CC->>Logger: log(info request_closed ReqId BinId Truck1)

        else Truck1 refuses

            Truck1->>CC: job_refuse(Truck1 BinId ReqId Token)

            CC->>CC: mark tried and retry

            CC->>Truck2: pickup_request(BinId ReqId Token)

            Note over Truck2: same accept flow as above

        end
    end

    Note over Logger: All log events are deduplicated within a time window
```
=======
>>>>>>> 348004b (readme update)

    Note over Bin: Bin periodically fills over time

    Bin->>Bin: increase_level()

    alt Bin becomes full

        Bin->>CC: bin_full(BinId, Token)
        Bin->>Logger: log(info, bin_full, BinId)

        CC->>CC: generate ReqId and select idle truck

        CC->>Truck1: pickup_request(BinId, ReqId, Token)

        CC->>Logger: log(info, pickup_request_sent, ReqId, BinId, Truck1)

        alt Truck1 accepts request

            Truck1->>CC: job_accept(Truck1, BinId, ReqId, Token)

            Truck1->>Logger: log(info, pickup_accept, BinId)

            CC->>CC: update state to awaiting_assign_ack

            CC->>Truck1: assignment(BinId, ReqId, Token)

            Truck1->>CC: assignment_ack(Truck1, BinId, ReqId, Token)

            CC->>CC: update state to awaiting_completion

            Note over Truck1: Truck moves toward bin

            Truck1->>Truck1: move for move_time ticks

            Note over Truck1: Waste collection phase

            Truck1->>Truck1: collect for collect_time ticks

            Truck1->>CC: collection_complete(BinId, ReqId, Token)

            CC->>CC: update state to awaiting_reset_ack

            CC->>Bin: reset_bin(BinId, ReqId, Token)

            Bin->>Bin: reset level to 0

            Bin->>CC: reset_ack(BinId, ReqId, Token)

            Bin->>Logger: log(info, bin_reset, BinId)

            CC->>CC: close request and clear inflight state

            CC->>Logger: log(info, request_closed, ReqId, BinId, Truck1)

        else Truck1 refuses request

            Truck1->>CC: job_refuse(Truck1, BinId, ReqId, Token)

            CC->>CC: mark truck as tried

            CC->>Truck2: pickup_request(BinId, ReqId, Token)

            Note over Truck2: Retry collection using another truck

        end
    end

    Note over Logger: Log events are deduplicated within a time window
```



<<<<<<< HEAD
## Key Features

- **Fully autonomous operation** — no polling or human triggers required once started
- **Fault-tolerant dispatch** — truck refusals and timeouts cause automatic retry with backoff
- **Idempotent message handling** — duplicate messages are safely ignored at every agent
- **TTL-based supervision** — four independently tunable timeout windows per request
- **Structured logging** — all lifecycle events emitted to a central logger with deduplication
- **Real-time dashboard** — WebSocket-based web UI streams live agent state and event log
- **Token authentication** — all messages validated against a shared secret before processing


## Technology Stack
=======
# 4. Technology Stack
>>>>>>> 348004b (readme update)

| Component | Technology |
|---|---|
| Agent platform | DALI — Dynamic Agent Logic and Interaction |
| Prolog runtime | SICStus Prolog 4.6 |
| Agent coordination | Linda tuple-space |
| Session management | tmux |
| Dashboard backend | Python 3 + FastAPI + WebSocket |
| Dashboard frontend | HTML5 + CSS + JavaScript |

---

# 5. Repository Layout

```text
SWMS_MAS_System/
├── src/                   # DALI platform source files
├── mas/
│   ├── types/             # Agent type definitions
│   │   ├── control_center.txt
│   │   ├── truck.txt
│   │   ├── smart_bin.txt
│   │   └── logger.txt
│   │
│   └── instances/         # Agent instance declarations
│
├── conf/                  # Communication configuration
├── build/                 # Compiled agent artifacts
├── tmp/                   # Runtime working files
├── log/                   # Agent log output
│
├── dashboard/
│   ├── bridge.py          # FastAPI WebSocket bridge
│   ├── start.sh
│   └── static/index.html  # Dashboard UI
│
├── startmas.sh            # MAS launcher
└── GAIA_Design_Documentation.md
```

---

# 6. Getting Started

## Prerequisites

Install the following dependencies before running the system:

- SICStus Prolog 4.6.x
- tmux
- Python 3.9+
- pip

Expected SICStus installation path:

```bash
/usr/local/sicstus4.6.0
```

---

## Launch the Multi-Agent System

```bash
# Start all agents
./startmas.sh
```

Enable dashboard mode:

```bash
DASHBOARD=1 ./startmas.sh
```

---

## Startup Process

The launcher script automatically:

1. Terminates existing DALI/SICStus processes
2. Starts the Linda tuple-space coordination server
3. Launches each agent in a dedicated tmux pane
4. Applies staggered startup timing
5. Performs automatic health checks

---

# 7. Dashboard

Start the dashboard server:

```bash
cd dashboard

pip install -r requirements.txt

./start.sh
```

Open the dashboard in a browser:

```text
http://localhost:8000
```

---

# 8. Configuration Parameters

Timing parameters can be modified in:

```text
mas/types/*.txt
```

| Parameter | Agent | Default | Description |
|---|---|---|---|
| `cycle_interval_ms` | ControlCenter | 1000 ms | Supervision cycle interval |
| `reply_ttl` | ControlCenter | 6 cycles | Wait time for truck response |
| `assign_ack_ttl` | ControlCenter | 6 cycles | Wait time for assignment acknowledgment |
| `completion_ttl` | ControlCenter | 10 cycles | Wait time for collection completion |
| `reset_ack_ttl` | ControlCenter | 3 cycles | Wait time for bin reset acknowledgment |
| `deltaT` | SmartBin | 2 s | Fill simulation interval |
| `fill_step` | SmartBin | 20% | Fill increment per cycle |
| `move_time` | Truck | 2 ticks | Simulated travel duration |
| `collect_time` | Truck | 1 tick | Simulated collection duration |

---

# 9. Fault Tolerance Features

The SWMS includes several resilience mechanisms:

- Automatic truck reassignment
- Request retry escalation
- Timeout supervision
- Message acknowledgment tracking
- Duplicate log suppression
- Stateful request monitoring
- Distributed autonomous recovery

These mechanisms ensure reliable operation even under partial communication failures.

---

# 10. Design Documentation

<<<<<<< HEAD





This project is developed for academic research purposes. See [`LICENSE`](LICENSE) for details.


=======
Complete GAIA-based agent design documentation is available in:

```text
GAIA_Design_Documentation.md
```

The documentation includes:

- Roles model
- Interaction model
- Agent responsibilities
- Organizational rules
- Event tables
- Action tables
- Protocol specifications

---

# 11. License

This project is developed for academic and research purposes.

See:

```text
LICENSE
```

for licensing details.
>>>>>>> 348004b (readme update)
