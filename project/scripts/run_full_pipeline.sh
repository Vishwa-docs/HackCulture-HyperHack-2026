#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== Needle Finder Pipeline ==="
echo "Start: $(date)"

# Check prerequisites
if [[ ! -f data/input/gauntlet.pdf ]]; then
    echo "ERROR: data/input/gauntlet.pdf not found"
    exit 1
fi

if [[ ! -f .env ]]; then
    echo "ERROR: .env file not found (copy .env.example and fill in keys)"
    exit 1
fi

TEAM_ID="${1:-hackculture}"

echo ""
echo "Team ID: $TEAM_ID"
echo ""

python3 -m src.cli run-all \
    --input data/input/gauntlet.pdf \
    --team-id "$TEAM_ID" \
    "$@"

echo ""
echo "=== Pipeline Complete ==="
echo "End: $(date)"
echo ""
echo "Outputs:"
ls -lh data/outputs/ 2>/dev/null || echo "  (no outputs yet)"
