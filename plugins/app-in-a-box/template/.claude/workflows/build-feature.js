export const meta = {
  name: 'build-feature',
  description: 'Opt-in, token-heavy feature build from an approved spec: plan, tests first, backend and mobile in parallel, hostile self-review with break-it checks, draft PR, then the pr-review workflow. Costs roughly 3-6x the build-feature skill.',
  whenToUse: 'Claude Code only, when the owner asks to build a specced ticket with the workflow. The build-feature skill is the default (and the only route in Codex).',
  phases: [
    { title: 'Plan', detail: 'read the spec, split the work by directory, name the branch' },
    { title: 'Tests', detail: 'FR→TC tests written first and watched failing' },
    { title: 'Build', detail: 'migration + backend and mobile adapter + screen, in parallel' },
    { title: 'Self-review', detail: 'break each key test on purpose; old-build and second-user checks' },
    { title: 'PR', detail: 'draft PR with real gate output, then the pr-review workflow' },
  ],
}

// args: a spec path (docs/product/specs/<ticket>-<slug>.md), or {spec: ...}.
const spec = (args && (args.spec || args)) || ''
if (!spec) {
  return { error: 'Pass the approved spec path. No spec yet? Run the feature-discovery skill first.' }
}

const PLAN = {
  type: 'object',
  properties: {
    ticket: { type: 'string' },
    branch: { type: 'string', description: '<type>/<ticket>-<slug>' },
    worktree: { type: 'string', description: 'absolute path of the worktree created for this feature' },
    has_migration: { type: 'boolean' },
    backend_tasks: { type: 'array', items: { type: 'string' } },
    mobile_tasks: { type: 'array', items: { type: 'string' } },
    wire_contract: { type: 'string', description: 'exact request/response shape both sides must agree on' },
    test_plan: { type: 'array', items: { type: 'string' }, description: 'TC-xx -> FR-xx -> test file' },
  },
  required: ['ticket', 'branch', 'worktree', 'backend_tasks', 'mobile_tasks', 'wire_contract', 'test_plan'],
}
const STEP = {
  type: 'object',
  properties: {
    done: { type: 'array', items: { type: 'string' } },
    gate: { type: 'string', description: 'the command run' },
    gate_passed: { type: 'boolean' },
    output_tail: { type: 'string', description: 'real last ~15 lines of the gate output' },
    blockers: { type: 'array', items: { type: 'string' } },
  },
  required: ['done', 'gate', 'gate_passed', 'output_tail', 'blockers'],
}

phase('Plan')
const plan = await agent(
  `Read the approved spec at ${spec} and docs/product/BRIEF.md. Find or confirm its ticket (backlog skill). ` +
    'Create the feature worktree with the new-worktree skill and report its absolute path. Split the work into ' +
    'backend tasks (supabase/migrations, backend/, tests/) and mobile tasks (mobile/), and pin the exact wire ' +
    'contract both sides will code against. Do not write feature code yet.',
  { schema: PLAN, agentType: 'lead-engineer', label: 'plan' },
)
if (!plan) return { error: 'Planning failed; run the build-feature skill instead.' }
const where = `Work ONLY inside the worktree ${plan.worktree} (branch ${plan.branch}). Spec: ${spec}. Wire contract: ${plan.wire_contract}. `

phase('Tests')
const tests = await agent(
  where + 'Write the tests from this test plan first (backend pytest; pure mobile logic in jest), run them, and ' +
    `confirm they FAIL for the right reason. Commit as \`test: ...\`. Plan: ${JSON.stringify(plan.test_plan)}`,
  { schema: STEP, agentType: 'qa-engineer', label: 'tests first' },
)

phase('Build')
// Backend and mobile touch disjoint directories and code against the pinned contract, so they can run at once.
const [backend, mobile] = await parallel([
  () =>
    agent(
      where + 'Backend half of build-feature steps 3-4 (.agents/skills/build-feature/SKILL.md): migration if any ' +
        '(additive, RLS, rollback in header), service, router scoped by user.id, Wire model. Touch only ' +
        'supabase/, backend/, tests/. Gate: `scripts/dev-venv.sh python -m pytest -q`. Commit when green. ' +
        `Tasks: ${JSON.stringify(plan.backend_tasks)}`,
      { schema: STEP, agentType: 'lead-engineer', phase: 'Build', label: 'backend' },
    ),
  () =>
    agent(
      where + 'Mobile half of build-feature steps 5-6: *Wire type + adapter in lib/api.ts, screen from components/ui ' +
        'primitives and tokens, view + success/failure analytics, loading/empty/error states, testIDs, Maestro ' +
        'happy-path flow. Touch only mobile/. Gate: `cd mobile && npm run gates`. Commit when green. ' +
        `Tasks: ${JSON.stringify(plan.mobile_tasks)}`,
      { schema: STEP, agentType: 'mobile-engineer', phase: 'Build', label: 'mobile' },
    ),
])
const blockers = [tests, backend, mobile].filter(Boolean).flatMap((s) => s.blockers)
if (!backend || !mobile || !backend.gate_passed || !mobile.gate_passed) {
  return {
    status: 'stopped before PR: a build half is red',
    worktree: plan.worktree,
    backend,
    mobile,
    blockers,
  }
}

phase('Self-review')
const hostile = await agent(
  where + 'Hostile self-review (build-feature step 7). For each important test: break the code on purpose (drop ' +
    'the user filter, pick the wrong row, skip a field), run it, confirm it goes red, restore. Check: a user on ' +
    "last month's app build, a request from a different user, a double tap on a slow network. Fix real gaps " +
    '(never weaken a test), re-run both gates, commit.',
  { schema: STEP, agentType: 'qa-engineer', effort: 'high', label: 'break-it checks' },
)

phase('PR')
const pr = await agent(
  where + 'Push the branch (`git push origin ' + plan.branch + '`, never a bare push) and open a DRAFT PR: title ' +
    `\`feat: <summary> (${plan.ticket})\`, body = spec link, what changed, and how it was verified with this real ` +
    'output: ' + JSON.stringify([tests, backend, mobile, hostile].filter(Boolean).map((s) => ({ gate: s.gate, tail: s.output_tail }))) +
    '. Return only the PR number.',
  { effort: 'low', label: 'open draft PR' },
)
let review = null
try {
  review = await workflow('pr-review', { pr: String(pr).trim() })
} catch (e) {
  log('pr-review workflow unavailable; run the pr-review skill on the PR')
}
return { ticket: plan.ticket, branch: plan.branch, worktree: plan.worktree, pr: String(pr).trim(), blockers, review }
