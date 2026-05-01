#!/bin/bash
# $1 = agent name (bare, e.g., smart_bin)
# $2 = DALI_HOME path

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMM_BASE="$SCRIPT_DIR/communication"

mkdir -p "$SCRIPT_DIR/mas"

agent_name="${1%.txt}"
agent_file="$agent_name.txt"
agent_base="$agent_name"

cat <<EOC > "$SCRIPT_DIR/mas/$agent_file"
agent('tmp/$agent_base','$agent_name','no',italian,
      ['$COMM_BASE'],
      ['$2/communication_fipa','$2/learning','$2/planasp'],
      'no',
      '$2/onto/dali_onto.txt',
      [startI]).
EOC
