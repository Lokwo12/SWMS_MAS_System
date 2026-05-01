#!/bin/bash
set -e
shopt -s nullglob

clear

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# --- USER CONFIG ---
SICSTUS_HOME=/usr/local/sicstus4.6.0
DALI_HOME="${DALI_HOME:-$SCRIPT_DIR/src}"
PROLOG="$SICSTUS_HOME/bin/sicstus"
BUILD_HOME="$SCRIPT_DIR/build"
INSTANCES_HOME="$SCRIPT_DIR/mas/instances"
TYPES_HOME="$SCRIPT_DIR/mas/types"
CONF_DIR="$SCRIPT_DIR/conf"
WAIT="sleep 8"
LINDA_PORT=3010
AUTO_HEALTHCHECK="${AUTO_HEALTHCHECK:-1}"
HEALTHCHECK_WAIT="${HEALTHCHECK_WAIT:-20}"
NO_ATTACH="${NO_ATTACH:-0}"
AGENT_START_STAGGER="${AGENT_START_STAGGER:-2}"
DASHBOARD="${DASHBOARD:-0}"

# --- ENVIRONMENT CHECK ---
if ! command -v tmux &> /dev/null; then
    echo "Error: tmux is required."
    exit 1
fi

if [[ ! -x "$PROLOG" ]]; then
    echo "Error: SICStus Prolog not found at $PROLOG"
    exit 1
fi

# --- CLEANUP ---
echo "Stopping existing agents..."
killall sicstus 2>/dev/null || true
tmux kill-session -t DALI_session 2>/dev/null || true
pkill -9 -f active_server_wi.pl 2>/dev/null || true
pkill -9 -x sicstus 2>/dev/null || true
if command -v fuser &> /dev/null; then
    fuser -k -9 ${LINDA_PORT}/tcp 2>/dev/null || true
fi

echo "Cleaning environment..."
rm -rf tmp/* tmp/.[!.]* tmp/..?* \
    build/* build/.[!.]* build/..?* \
    work/* work/.[!.]* work/..?* \
    conf/mas/* conf/mas/.[!.]* conf/mas/..?*
mkdir -p tmp build work conf/mas log
> "$SCRIPT_DIR/log/logger_events.txt"

# --- SELECT FREE LINDA PORT ---
while ss -ltnH "sport = :${LINDA_PORT}" 2>/dev/null | grep -q .; do
    LINDA_PORT=$((LINDA_PORT + 1))
done
echo "Using LINDA port: ${LINDA_PORT}"

# --- BUILD AGENTS ---
echo "Building agent instances..."
for instance_path in $INSTANCES_HOME/*.txt; do
    instance_filename=$(basename "$instance_path")          # e.g., smart_bin.txt
    agent_name="${instance_filename%.txt}"                  # bare name
    agent_type=$(tr -d '\r' < "$instance_path")
    type_file="$TYPES_HOME/$agent_type.txt"

    if [[ -f "$type_file" ]]; then
        echo "Creating agent $agent_name (Type: $agent_type)"
        cat "$type_file" > "$BUILD_HOME/$agent_name.txt"
    else
        echo "Warning: Type file $type_file not found for $agent_name"
    fi
done

# Copy built agents to work folder
files=($BUILD_HOME/*.txt)
if [ ${#files[@]} -gt 0 ]; then
    cp "${files[@]}" work/
    cp "${files[@]}" tmp/
fi

# --- START LINDA SERVER ---
echo "Starting LINDA Server..."
server_ready=0
server_pane_id=""
for _ in $(seq 1 10); do
    srvcmd="$PROLOG --noinfo -l $DALI_HOME/active_server_wi.pl --goal \"go(${LINDA_PORT},'server.txt').\""
    tmux new-session -d -s DALI_session -n "DALI_MAS" "$srvcmd"
    server_pane_id="$(tmux list-panes -t DALI_session -F '#{pane_id}' | head -n1)"

    echo "Waiting for LINDA Server on port ${LINDA_PORT}..."
    $WAIT

    if tmux capture-pane -pt "$server_pane_id" -S -80 | grep -Eq "SPIO_E_NET_ADDRINUSE|goal failed"; then
        tmux kill-session -t DALI_session 2>/dev/null || true
        LINDA_PORT=$((LINDA_PORT + 1))
        continue
    fi

    server_ready=1
    break
done

if [ "$server_ready" -ne 1 ]; then
    echo "Error: LINDA Server failed to start correctly after multiple ports."
    exit 1
fi

tmux set-option -t DALI_session -g pane-border-status top
tmux set-option -t DALI_session -g pane-border-format '#{pane_title}'
tmux select-pane -t "$server_pane_id" -T "LINDA_SERVER"

# Keep endpoint file consistent for runtimes resolving paths from src/
cp -f server.txt src/server.txt

# --- LAUNCH ALL MAS AGENTS (smart bins first for fast dashboard visibility) ---
launch_agent() {
    local agent_name="$1"
    echo "Launching agent: $agent_name"

    # Generate proper config (conf/mas/agent_name.txt)
    "$CONF_DIR/makeconf.sh" "$agent_name" "$DALI_HOME"

    # Logger output is always tee'd so the dashboard bridge can read it
    local run_cmd
    if [[ "$agent_name" == "logger" ]]; then
        run_cmd="$CONF_DIR/startagent.sh $agent_name $PROLOG $DALI_HOME 2>&1 | tee -a $SCRIPT_DIR/log/logger_events.txt"
    else
        run_cmd="$CONF_DIR/startagent.sh $agent_name $PROLOG $DALI_HOME"
    fi

    tmux split-window -v -t DALI_session "$run_cmd"
    tmux select-pane -t DALI_session -T "$agent_name"
    tmux select-layout -t DALI_session tiled
    sleep "$AGENT_START_STAGGER"
}

reorder_tmux_panes() {
    local session="$1"
    local desired=(
        "LINDA_SERVER"
        "control_center"
        "logger"
        "smart_bin1"
        "smart_bin2"
        "smart_bin3"
        "truck1"
        "truck2"
        "truck3"
    )

    local first_index
    first_index="$(tmux list-panes -t "$session" -F '#{pane_index}' | sort -n | head -n1)"
    [[ -z "$first_index" ]] && return 0

    local i
    local target_title
    local current_pane_id
    local target_pane_id
    local target_idx
    for i in "${!desired[@]}"; do
        target_title="${desired[$i]}"
        current_pane_id="$(tmux list-panes -t "$session" -F '#{pane_id}|#{pane_title}' | awk -F '|' -v t="$target_title" '$2==t {print $1; exit}')"
        if [[ -z "$current_pane_id" ]]; then
            continue
        fi

        target_idx=$((first_index + i))
        target_pane_id="$(tmux list-panes -t "$session" -F '#{pane_index}|#{pane_id}' | awk -F '|' -v idx="$target_idx" '$1==idx {print $2; exit}')"
        if [[ -z "$target_pane_id" ]]; then
            continue
        fi

        if [[ "$current_pane_id" != "$target_pane_id" ]]; then
            tmux swap-pane -s "$current_pane_id" -t "$target_pane_id" 2>/dev/null || true
        fi
    done

    tmux select-layout -t "$session" tiled
}

ordered_agents=(
    "logger"
    "control_center"
    "smart_bin1"
    "smart_bin2"
    "smart_bin3"
    "truck1"
    "truck2"
    "truck3"
)

for agent_name in "${ordered_agents[@]}"; do
    if [[ -f "$BUILD_HOME/$agent_name.txt" ]]; then
        launch_agent "$agent_name"
        if [[ "$agent_name" == "control_center" ]]; then
            sleep 6
        fi
    fi
done

for agent_file in $BUILD_HOME/*.txt; do
    agent_name=$(basename "$agent_file" .txt)
    skip=0
    for ordered in "${ordered_agents[@]}"; do
        if [[ "$agent_name" == "$ordered" ]]; then
            skip=1
            break
        fi
    done
    [[ "$skip" -eq 1 ]] && continue
    launch_agent "$agent_name"
done

reorder_tmux_panes DALI_session

if [[ "$AUTO_HEALTHCHECK" == "1" && -x "$SCRIPT_DIR/healthcheck.sh" ]]; then
    echo "Running health check in background..."
    WAIT_SECONDS="$HEALTHCHECK_WAIT" "$SCRIPT_DIR/healthcheck.sh" DALI_session > "$SCRIPT_DIR/tmp/healthcheck.last.log" 2>&1 &
    echo "Health check log: tmp/healthcheck.last.log"
fi

echo "All agents launched. Attaching tmux..."
tmux select-layout -t DALI_session tiled

if [[ "$DASHBOARD" == "1" ]]; then
    echo "Starting web dashboard bridge on port 8000..."
    DASH_VENV="$SCRIPT_DIR/dashboard/.venv"
    if ! "$DASH_VENV/bin/python3" -c "import uvicorn" 2>/dev/null; then
        echo "[dashboard] Installing dependencies into .venv ..."
        python3 -m venv --clear "$DASH_VENV"
        "$DASH_VENV/bin/pip" install -q -r "$SCRIPT_DIR/dashboard/requirements.txt"
    fi
    cd "$SCRIPT_DIR/dashboard"
    nohup "$DASH_VENV/bin/python3" -m uvicorn bridge:app --host 0.0.0.0 --port 8000 \
        > "$SCRIPT_DIR/log/dashboard.log" 2>&1 &
    cd "$SCRIPT_DIR"
    echo "Dashboard: http://localhost:8000  (log: log/dashboard.log)"
fi

if [[ "$NO_ATTACH" == "1" ]]; then
    echo "NO_ATTACH=1 set: MAS started in background tmux session DALI_session"
    exit 0
fi

tmux attach -t DALI_session