export const meta = {
  name: 'pr-review',
  description: 'Opt-in, token-heavy PR review: gates, 4 parallel reviewers, 2-lens adversarial verify, bounded fix loop, chair ruling, plain-English verdict. Costs roughly 5-10x the pr-review skill.',
  whenToUse: 'Claude Code only, when the owner asks for the thorough/workflow review of a PR. The pr-review skill is the default (and the only route in Codex).',
  phases: [
    { title: 'Gates', detail: 'resolve the PR, run the deterministic gates the diff touches' },
    { title: 'Review', detail: 'correctness/security, design+a11y, analytics+env, tests: in parallel' },
    { title: 'Verify', detail: 'two skeptics per blocker/major try to refute it' },
    { title: 'Fix', detail: 'safe fixes only, re-run gates, at most 3 rounds' },
    { title: 'Chair', detail: 'independent ruling before anything merges', model: 'fable' },
  ],
}

// args: a PR number / URL / branch, or {pr: ...}. Default: the current branch's PR.
const target = (args && (args.pr || args)) || 'the PR for the current branch'

const GATES = {
  type: 'object',
  properties: {
    pr: { type: 'string', description: 'PR number, or empty if none exists' },
    title: { type: 'string' },
    base: { type: 'string' },
    head: { type: 'string' },
    is_draft: { type: 'boolean' },
    changed_files: { type: 'array', items: { type: 'string' } },
    gates: {
      type: 'array',
      items: {
        type: 'object',
        properties: { name: { type: 'string' }, passed: { type: 'boolean' }, output_tail: { type: 'string' } },
        required: ['name', 'passed'],
      },
    },
  },
  required: ['pr', 'changed_files', 'gates'],
}
const FINDINGS = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          severity: { type: 'string', enum: ['blocker', 'major', 'minor'] },
          file: { type: 'string' },
          line: { type: 'integer' },
          what: { type: 'string' },
          scenario: { type: 'string', description: 'inputs -> wrong result, for whom' },
          safe_to_autofix: { type: 'boolean' },
        },
        required: ['severity', 'file', 'what', 'scenario', 'safe_to_autofix'],
      },
    },
  },
  required: ['findings'],
}
const VERDICT = {
  type: 'object',
  properties: { refuted: { type: 'boolean' }, reason: { type: 'string' } },
  required: ['refuted', 'reason'],
}
const FIXED = {
  type: 'object',
  properties: {
    fixed: { type: 'array', items: { type: 'string' } },
    not_fixed: { type: 'array', items: { type: 'string' } },
    gates_green: { type: 'boolean' },
    gate_output_tail: { type: 'string' },
  },
  required: ['fixed', 'not_fixed', 'gates_green'],
}

phase('Gates')
const g = await agent(
  `Resolve ${target} with \`gh pr view --json number,title,headRefName,baseRefName,isDraft,files\`. ` +
    'If no PR exists return pr="" and empty arrays. Otherwise check out its head branch, then run ONLY the ' +
    'deterministic gates the changed files touch, exactly as section 1 of .agents/skills/pr-review/SKILL.md ' +
    'lists them. Report each gate with the real last ~20 lines of output. Do not fix anything.',
  { schema: GATES, effort: 'low', label: 'resolve + gates' },
)
if (!g || !g.pr) {
  return { verdict: 'No PR found for ' + target + '. Open one first (backlog skill → branch → draft PR).' }
}
const red = g.gates.filter((x) => !x.passed)
log(`PR #${g.pr}: ${g.changed_files.length} files, ${red.length} red gate(s)`)

phase('Review')
const context =
  `PR #${g.pr} (${g.title}), diff = \`git diff origin/${g.base || 'main'}...HEAD\`. ` +
  `Changed files: ${g.changed_files.join(', ')}. Red gates: ${red.map((x) => x.name).join(', ') || 'none'}. `
const LENSES = [
  { name: 'correctness+security', agentType: 'correctness-reviewer', ask: 'Pass 1 (correctness + security, incl. IDOR / missing user_id scoping and breaking wire changes).' },
  { name: 'design+a11y', agentType: 'design-a11y-reviewer', ask: 'Pass 2 (design system + accessibility). Skip if no mobile/app or mobile/components files changed.' },
  { name: 'analytics+env', agentType: null, ask: 'Pass 3 (analytics + env wiring: view events, success+failure pairs, unwired env vars).' },
  { name: 'tests', agentType: 'qa-engineer', ask: 'Pass 4 (tests: is new behaviour tested, and would each key test fail if the code were wrong?). Read-only for this pass.' },
]
const rounds = await parallel(
  LENSES.map((l) => () =>
    agent(
      context + `Do review ${l.ask} from .agents/skills/pr-review/SKILL.md section 2. ` +
        'Report only findings you can point at a file:line. Mark safe_to_autofix only for the "safe" class in section 4.',
      { schema: FINDINGS, phase: 'Review', label: l.name, ...(l.agentType ? { agentType: l.agentType } : {}) },
    ),
  ),
)
// Barrier on purpose: dedupe across all reviewers before paying for verification.
const seen = new Set()
const all = []
for (const r of rounds.filter(Boolean)) {
  for (const f of r.findings) {
    const key = `${f.file}:${f.line || 0}:${f.what.slice(0, 40)}`
    if (!seen.has(key)) {
      seen.add(key)
      all.push(f)
    }
  }
}
const serious = all.filter((f) => f.severity !== 'minor')
log(`${all.length} finding(s), ${serious.length} blocker/major to verify`)

phase('Verify')
const judged = await pipeline(serious, (f) =>
  parallel(
    ['does it reproduce on the real code path', 'is it actually reachable by a user or an old app build'].map((lens) => () =>
      agent(
        `Try to REFUTE this review finding by re-reading the code (lens: ${lens}). ` +
          `Finding: [${f.severity}] ${f.file}:${f.line || '?'}: ${f.what}. Scenario: ${f.scenario}. ` +
          'Default to refuted=true if you cannot confirm it from the code.',
        { schema: VERDICT, phase: 'Verify', effort: 'high', label: `verify ${f.file}` },
      ),
    ),
  ).then((votes) => ({ f, survives: votes.filter(Boolean).filter((v) => !v.refuted).length === 2 })),
)
const confirmed = judged.filter((j) => j && j.survives).map((j) => j.f)
const dropped = serious.length - confirmed.length
if (dropped) log(`${dropped} finding(s) refuted and dropped`)

phase('Fix')
let fixable = confirmed.filter((f) => f.safe_to_autofix)
const fixedAll = []
let gatesGreen = red.length === 0
let lastTail = ''
for (let round = 1; round <= 3 && (fixable.length || !gatesGreen); round++) {
  const res = await agent(
    context +
      `Round ${round}/3. Fix ONLY these verified, safe findings and mechanical gate failures, following section 4 of ` +
      '.agents/skills/pr-review/SKILL.md (never weaken/delete a test, never disable a lint rule, never change ' +
      'behaviour, schema or wire shape). Commit as `fix(review): <what>` on the PR head branch, then re-run the ' +
      `gates and report. Findings: ${JSON.stringify(fixable)}. Red gates: ${JSON.stringify(red.map((x) => x.name))}.`,
    { schema: FIXED, phase: 'Fix', label: `fix round ${round}` },
  )
  if (!res) break
  fixedAll.push(...res.fixed)
  const progressed = res.fixed.length > 0 || (res.gates_green && !gatesGreen)
  gatesGreen = res.gates_green
  lastTail = res.gate_output_tail || lastTail
  fixable = fixable.filter((f) => !res.fixed.some((x) => x.includes(f.file)))
  if (!progressed) {
    log('No progress this round: stopping the fix loop')
    break
  }
}
const leftover = confirmed.filter((f) => !fixedAll.some((x) => x.includes(f.file)))

phase('Chair')
const ruling = await agent(
  `Rule on PR #${g.pr}. Read the diff yourself first (\`git diff origin/${g.base || 'main'}...HEAD\`), ` +
    'then these inputs. Gates green after fixes: ' + gatesGreen + '. Unresolved verified findings: ' +
    JSON.stringify(leftover) + '. Fixed: ' + JSON.stringify(fixedAll) + '. ' +
    'Risky if it touches auth/RLS, a migration, secrets/env/CI/build config, deletes files, or is > ~400 net lines.',
  { agentType: 'chair', phase: 'Chair', label: 'chair ruling' },
)

return {
  pr: g.pr,
  gates_green: gatesGreen,
  last_gate_output: lastTail,
  fixed: fixedAll,
  unresolved: leftover,
  minor: all.filter((f) => f.severity === 'minor'),
  refuted_count: dropped,
  chair: ruling,
  next_step:
    'Main session: write the plain-English verdict from section 5 of the pr-review skill, post it as a PR ' +
    'comment, and merge only under the rules there (owner opted in, low risk, green CI, chair did not ESCALATE).',
}
