#!/usr/bin/env bash

# Check if qluent is installed and configured.
# Returns additionalContext to Claude with setup status.

STATUS=""
WARNINGS=""

# Check if qluent binary is available
if ! command -v qluent &>/dev/null; then
  STATUS="not_installed"
  WARNINGS="qluent CLI is not installed. Run: npm install -g @qluent/cli"
else
  # Check if config exists by running qluent config (no args = print current config)
  CONFIG_OUTPUT=$(qluent config 2>&1)
  EXIT_CODE=$?

  if [ $EXIT_CODE -ne 0 ] || echo "$CONFIG_OUTPUT" | grep -q "No config file found"; then
    STATUS="not_configured"
    WARNINGS="qluent CLI is installed but not configured. Run: qluent login (recommended) or qluent setup"
  else
    # Check for required fields
    MISSING=""
    echo "$CONFIG_OUTPUT" | grep -q "api_key:" || MISSING="$MISSING api_key"
    echo "$CONFIG_OUTPUT" | grep -q "project_uuid:" || MISSING="$MISSING project_uuid"

    if [ -n "$MISSING" ]; then
      STATUS="partially_configured"
      WARNINGS="qluent config is missing:$MISSING. Run: qluent setup"
    else
      STATUS="ready"
    fi
  fi
fi

if [ "$STATUS" = "ready" ]; then
  cat << 'EOF'
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "Qluent CLI is installed and configured. Available metric tree commands: investigate, trend, evaluate, compare, rca analyze. Always start with `investigate` for KPI questions."
  }
}
EOF
else
  cat << DYNEOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "Qluent CLI status: ${STATUS}. ${WARNINGS}. The qluent plugin is loaded but the CLI needs setup before metric analysis commands will work. Inform the user proactively."
  }
}
DYNEOF
fi

exit 0
