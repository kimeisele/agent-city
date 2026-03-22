# Federation Architect Dispatch: Phase 1 (The Return Channel)

**To the receiving Agent:** 
You have been summoned in a broader workspace (e.g., `/Users/ss/projects/`) with native tool access to both `steward` and `agent-city`. Your prime directive is to execute **Phase 1: The Return Channel**, plugging a massive Nadi API spam leak.

## Context & Background
Currently, when `agent-city` hits a code scope gate, it sends a `bottleneck_escalation` message via Nadi to `steward`. `steward` receives it, creates a local `[BOTTLENECK_ESCALATION]` task, and resolves it natively. 
**The Problem:** `steward` never emits a confirmation back to Nadi. Because `agent-city` never receives a `bottleneck_resolution` message, its local scope gate stays permanently blocked, looping infinitely and burning GitHub API limits with redundant escalations.

## Implementation Guide (No Spaghetti allowed)

### 1. The Emitter (`steward` repository)
We must gracefully intercept the completion of `[BOTTLENECK_ESCALATION]` tasks and emit the resolution.
- **Target Location:** Look inside `steward/steward/hooks/karma.py` (which already sweeps completed tasks via `task_mgr.list_tasks(status=TaskStatus.COMPLETED)`) or the execution loop in `steward/steward/federation.py`.
- **Logic:**
  1. Iterate over tasks marked `TaskStatus.COMPLETED`.
  2. If `task.title.startswith("[BOTTLENECK_ESCALATION]")`, extract the `dedup_key`. The dedup key is reliably saved in the task's `description` field when it is created in `_handle_bottleneck_escalation` (e.g. `dedup_key: {hash}`).
  3. Formulate a payload: `{"op": "bottleneck_resolution", "payload": {"dedup_key": task_dedup_key}}`.
  4. Use the `NadiHub` or `FederationNadi` transport layer to emit this message to `agent-city`.

### 2. The Receiver (`agent-city` repository)
We must consume the resolution and unblock the simulated active city.
- **Target Location:** Look at `city/hooks/genesis/federation.py` (which handles `FederationNadiHook` directives) or `city/membrane.py` (where Nadi messages enter the ingress surface).
- **Logic:**
  1. Add a handler for `bottleneck_resolution`.
  2. The payload will contain the `dedup_key`. 
  3. Query `ctx.sankalpa.registry.get_active_missions()` or the city's bottleneck cache to find the blocked mission tied to that `dedup_key`. 
  4. Mark the mission/bottleneck as resolved.

Good hunting. Maintain strict architectural boundaries.
