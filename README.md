# SWMS — Smart Waste Management System

> A fully autonomous Multi-Agent System for urban waste collection, built on the **DALI** logic agent platform (SICStus Prolog).

---

## Overview

When a smart bin reaches maximum capacity, the system automatically:

1. Detects the fill event and opens a tracked collection request
2. Selects the best available truck through a fault-tolerant dispatch protocol
3. Supervises the truck's movement and collection phases via TTL-based timeout monitoring
4. Resets the bin to operational state once collection is confirmed

The entire workflow runs without human intervention and is resilient to truck refusals, delayed acknowledgements, lost messages, and collection timeouts — all handled directly inside the DALI agent logic.

---

## Architecture

```text
┌─────────────────────────────────────────────────────┐
│                 MANAGEMENT LAYER                    │
│     ControlCenter (Coordinator / Supervisor)        │
└────────────────────┬────────────────────────────────┘
                     │  task delegation
          ┌──────────┴──────────┐
          ▼                     ▼
┌──────────────────┐   ┌────────────────────────┐
│   FIELD LAYER    │   │    SENSING LAYER        │
│   Truck ×3       │   │    SmartBin ×3          │
└──────────────────┘   └────────────────────────┘
          │                     │
          └──────────┬──────────┘
                     ▼
           ┌────────────────────┐
           │   SUPPORT LAYER    │
           │     Logger ×1      │
           └────────────────────┘
```

---

## Agents

| Agent | Instances | Role |
|---|---|---|
| `control_center` | 1 | Coordinator and request lifecycle supervisor |
| `truck1`, `truck2`, `truck3` | 3 | Waste collection executors |
| `smart_bin1`, `smart_bin2`, `smart_bin3` | 3 | Sensing bins — fill, alert, and reset |
| `logger` | 1 | Centralized event logger with deduplication |

---

## Collection Workflow

```mermaid
sequenceDiagram
    participant Bin as SmartBin
    participant CC as ControlCenter
    participant Truck1 as Truck_First
    participant Truck2 as Truck_Second
    participant Logger

    Note over Bin: Periodically fills up

    Bin->>Bin: increase_level()

    alt Bin becomes full
        Bin->>CC: bin_full(BinId, Token)
        Bin->>Logger: log(info, bin_full, BinId)

        CC->>CC: generate ReqId
        CC->>CC: select idle truck

        CC->>Truck1: pickup_request(BinId, ReqId, Token)
        CC->>Logger: log(info, pickup_request_sent, ReqId)

        alt Truck1 accepts

            Truck1->>CC: job_accept(Truck1, BinId, ReqId, Token)
            Truck1->>Logger: log(info, pickup_accept, BinId)

            CC->>CC: update_state(awaiting_assign_ack)

            CC->>Truck1: assignment(BinId, ReqId, Token)

            Truck1->>CC: assignment_ack(Truck1, BinId, ReqId, Token)

            CC->>CC: update_state(awaiting_completion)

            Note over Truck1: move() timer

            Truck1->>Truck1: move() for move_time ticks

            Note over Truck1: collect() timer

            Truck1->>Truck1: collect() for collect_time ticks

            Truck1->>CC: collection_complete(BinId, ReqId, Token)

            CC->>CC: update_state(awaiting_reset_ack)

            CC->>Bin: reset_bin(BinId, ReqId, Token)

            Bin->>Bin: reset level to 0

            Bin->>CC: reset_ack(BinId, ReqId, Token)

            Bin->>Logger: log(info, bin_reset, BinId)

            CC->>CC: close_request()

            CC->>Logger: log(info, request_closed, ReqId)

        else Truck1 refuses

            Truck1->>CC: job_refuse(Truck1, BinId, ReqId, Token)

            CC->>CC: mark_tried(BinId, Truck1)

            CC->>Truck2: pickup_request(BinId, ReqId, Token)

            Note over Truck2: same accept flow as above

        end
    end

    Note over Logger: Log events are deduplicated within a time window
```
---

## Technology Stack

| Component | Technology |
|---|---|
| Agent platform | DALI — Dynamic Agent Logic and Interaction |
| Prolog runtime | SICStus Prolog 4.6 |
| Agent coordination | Linda tuple-space |
| Session management | tmux |
| Dashboard backend | Python 3 + FastAPI + WebSocket |
| Dashboard frontend | HTML5 + CSS + JavaScript |

---

## Repository Layout

```text
SWMS_MAS_System/
├── src/                   # DALI platform source files
├── mas/
│   ├── types/             # Agent type definitions (.txt)
│   └── instances/         # Agent instance declarations
├── conf/                  # Communication configuration
├── build/                 # Compiled agent artifacts
├── tmp/                   # Runtime working files
├── log/                   # Agent log output
├── dashboard/
│   ├── bridge.py          # FastAPI WebSocket bridge
│   ├── start.sh
│   └── static/index.html  # Dashboard UI
├── startmas.sh            # MAS launcher
└── GAIA_Design_Documentation.md
```

---

## Getting Started

### Prerequisites

- SICStus Prolog 4.6.x (expected at `/usr/local/sicstus4.6.0`)
- tmux
- Python 3.9+

### Launch the MAS

```bash
./startmas.sh
```

With dashboard:

```bash
DASHBOARD=1 ./startmas.sh
```

### Launch the Dashboard

```bash
cd dashboard
pip install -r requirements.txt
./start.sh
```

Open `http://localhost:8000` in a browser.

---

## Configuration

Timing parameters are set in `mas/types/*.txt`:

| Parameter | Agent | Default | Description |
|---|---|---|---|
| `cycle_interval_ms` | ControlCenter | 1000 ms | Supervision cycle interval |
| `reply_ttl` | ControlCenter | 6 cycles | Timeout waiting for truck response |
| `assign_ack_ttl` | ControlCenter | 6 cycles | Timeout waiting for assignment ack |
| `completion_ttl` | ControlCenter | 10 cycles | Timeout waiting for collection |
| `reset_ack_ttl` | ControlCenter | 3 cycles | Timeout waiting for bin reset ack |
| `deltaT` | SmartBin | 2 s | Fill simulation interval |
| `fill_step` | SmartBin | 20% | Fill increment per cycle |
| `move_time` | Truck | 2 ticks | Simulated travel duration |
| `collect_time` | Truck | 1 tick | Simulated collection duration |

---

## Design Documentation

Full GAIA-based agent design — roles, interaction model, event tables, action tables, and protocol specifications — is in:

[GAIA_Design_Documentation.md](GAIA_Design_Documentation.md)

---

## License

Developed for academic and research purposes.
