# TASK 02 Review Fix Handoff

## Final status

- Branch: `main`
- HEAD before this handoff: `81079233ec344e620d224a173b65edc39163b284`
- Current uncommitted changes: Review Fix code, tests, report, and this handoff.
- No Review Fix commit or push has been performed.

## Architecture after fix

```text
graph.invoke(initial_state, context=RuntimeContext)
  -> validate_input(Runtime)
  -> investigator(State Evidence + action summary)
  -> ToolNode(ToolRuntime.context)
  -> collect_evidence(new normalized Evidence only)
  -> conditional routing
       sufficient -> deterministic triage -> make_output -> END
       insufficient -> investigator
       max rounds -> guardrail fallback -> make_output -> END
```

`AgentState` uses `MessagesState`; `RuntimeContext` contains `log_path`, `knowledge_base`, and `max_investigation_rounds`. Tools read these through `ToolRuntime` and do not expose them as model arguments.

Evidence now contains a TestSpec `EXPECTATION` fact (`expected_action`), log `OBSERVATION` facts (`fault` and `actual_action`), and knowledge `KNOWLEDGE` facts. `evidence_reducer` is the only old-plus-new merge operation; `collect_evidence` only fingerprints and returns current updates. Triage and sufficiency consume the business keys, not query strings.

## Invariant results

| Invariant | Result | Evidence |
|---|---|---|
| Runtime Context | PASS | `StateGraph(..., context_schema=RuntimeContext)`, `Runtime`, `ToolRuntime`, invocation `context=` |
| Structured Evidence input | PASS | Investigator prompt includes serialized current Evidence |
| Query/Evidence decoupling | PASS | `query_logs_to_evidence` emits `fault` / `actual_action` |
| Unified Evidence layer | PASS | `expectation_to_evidence`, log and knowledge converters, Triage consumes all three |
| Single reducer source | PASS | `collect_evidence` returns `evidence_reducer([], updates)` only; State reducer merges |
| UNKNOWN vs ABSENT | PASS | no Evidence remains UNKNOWN; empty target query emits `present=False` |
| LLM Triage boundary | PASS | `deterministic_triage` and `guardrail_fallback` are code paths |

Duplicate action awareness is implemented as an Investigator prompt summary of existing `ToolMessage` names and IDs. A separate general cache or automatic duplicate-call blocker was not added.

## Test matrix

- Deterministic checks: Triage conflict, input parsing, Evidence normalization, deduplication, UNKNOWN/ABSENT.
- Fake-model Graph checks: invalid input, max-round fallback, first-round early stop followed by further investigation, streaming path.
- Real LLM integration: all 10 existing logs using `ChatDeepSeek(model=DEEPSEEK_MODEL)` and `.invoke(...)`.
- LLM output fallback: `TimeoutError` model.
- Runtime context: same compiled graph invocation with different contexts was exercised during Phase A verification; the recorded tool result changed with the selected log.

## Actual final test

Command:

```bash
/opt/miniconda3/envs/helloagent/bin/python -m py_compile src/agent_02/*.py tests/test_02/*.py
source env.sh && /opt/miniconda3/envs/helloagent/bin/python -m unittest tests.test_02.test_agent -v
```

Result:

```text
Ran 3 tests in 49.305s
OK
```

Report summary:

```json
{
  "full_chain_passed": true,
  "full_chain_count": 10,
  "timeout_fallback_passed": true,
  "supplemental_passed": true
}
```

## Before / after

- Before: single-run dependencies were captured in `build_graph` closures; after: invocation context is passed through LangGraph Runtime.
- Before: log query strings became Evidence keys; after: deterministic parsing produces business facts.
- Before: TestSpec expectation was outside the Evidence layer; after: it is an `EXPECTATION` Evidence.
- Before: `collect_evidence` merged old and new state; after: State reducer is the merge source of truth.
- Before: Investigator did not explicitly receive Evidence or action summary; after: both are included in its prompt.
- Before: input tests only covered a missing log path; after: raw TestSpec boundary cases and invalid runtime limits are tested.

## Known risks and unresolved items

- The test module still makes the 10-case real LLM integration run in `setUpClass`; network and provider behavior can make it slow or unavailable.
- The current automated tests do not expose `collect_evidence` as an independently callable production function; single-consumption behavior is exercised through helper/reducer checks and Graph behavior, but a direct node-level assertion is `Not fully isolated`.
- Tool result content is JSON-decoded in `graph.py`; malformed Tool output raises rather than producing a structured error Evidence.
- The log parser intentionally handles only the specified regular format and does not solve complex multi-fault correlation.
- `ruff`, `mypy`, `pytest`, and coverage were not run: `Not verified`.

## Reviewer reading order

1. `src/agent_02/graph.py` — Runtime, ToolNode, Investigator loop and routing.
2. `src/agent_02/tools.py` — ToolRuntime context injection and tool behavior.
3. `src/agent_02/evidence.py` — normalization, fingerprint and reducer.
4. `src/agent_02/triage.py` — deterministic business rules.
5. `src/agent_02/models.py` — State and input contracts.
6. `tests/test_02/test_agent.py` — deterministic, fake-model and real-LLM tests.
7. `tests/test_02/test_report.json` — recorded execution evidence.
