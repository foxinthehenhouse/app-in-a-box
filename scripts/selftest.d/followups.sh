# Dogfood follow-ups: sourced by selftest.sh with $KIT, $APP, $T and check/refuses.

# The activity log never records a secret: feed the real capture hook commands, Grep
# patterns and fetched URLs carrying planted secrets, then search the log for them.
_capture_redacts() {
  local st="$T/capture-state" payload
  rm -rf "$st" && mkdir -p "$st"
  for payload in \
    '{"tool_name":"Bash","tool_input":{"command":"curl -H \"Authorization: Basic c2VrcmV0UGxhbnQx\" https://api.x.io"}}' \
    '{"tool_name":"Bash","tool_input":{"command":"curl https://api.x.io/v1?access_token=sekretValue2&x=1"}}' \
    '{"tool_name":"Grep","tool_input":{"pattern":"sk-ant-sekretValue3abc"}}' \
    '{"tool_name":"WebFetch","tool_input":{"url":"https://hooks.x.io/in?token=sekretValue4","prompt":"x"}}' \
    '{"tool_name":"Bash","tool_input":{"command":"gh secret set X --body sekretValue5"}}'; do
    printf '%s' "$payload" | APPBOX_STATE_DIR="$st" CLAUDE_PROJECT_DIR="$APP" bash "$APP/.claude/hooks/capture-activity.sh" || return 1
  done
  local log; log=$(find "$st" -name "*-activity.md" -exec cat {} + 2>/dev/null) || return 1
  [ -n "$log" ] || return 1                       # something was logged at all
  echo "$log" | grep -q 'redacted' || return 1     # and redaction ran
  ! echo "$log" | grep -q 'sekretValue'
}
check "capture hook redacts Basic auth, URL tokens, Grep patterns, fetched URLs, --body" "_capture_redacts"

check "a 401 only ends the session it was sent under" \
  "grep -q 'res.sentAs === (await currentUserId())' '$APP/mobile/lib/api.ts' \
   && grep -q 'A.s request 401s after B signed in' '$APP/mobile/lib/__tests__/api-401.test.ts'"
