#!/bin/bash
# $1 = agent name (bare, e.g., smart_bin)
# $2 = SICStus path
# $3 = DALI_HOME path

set -e

# Normalize agent name (accepts truck1 or truck1.txt)
AGENT_NAME="${1%.txt}"
AGENT_FILE="$AGENT_NAME.txt"

echo "Launching agent instance: $AGENT_FILE"

# Launch agent
$2 --noinfo -l "$3/active_dali_wi.pl" --goal "start0('conf/mas/$AGENT_FILE')."