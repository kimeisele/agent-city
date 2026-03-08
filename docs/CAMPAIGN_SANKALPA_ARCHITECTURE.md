## Campaign-driven Sankalpa

`agent-city` already had missions, heartbeat, and reflection, but not a durable campaign spine above them.

This layer adds a minimal long-horizon loop:

1. **Campaign** stores a north star plus success signals.
2. **DHARMA heartbeat** evaluates the current city state against those signals.
3. **Gap compiler** opens a bounded GitHub issue and creates a normal `issue_*` Sankalpa mission.
4. **KARMA** executes through the existing issue mission path.
5. **MOKSHA** reflects and the next heartbeat re-evaluates the campaign.

### Ownership boundary

- `agent-city`: owns campaign state and heartbeat evaluation
- `agent-internet`: can later project campaign summaries, but does not own them
- `steward-protocol`: remains ingress/verification/edge, not campaign truth

### Why issues first?

KARMA already knows how to execute `issue_*` missions. Reusing that path avoids inventing a second mission dialect.

### First supported campaign signals

- `heartbeat_healthy`
- `chain_valid`
- `active_missions_at_most`

This is intentionally small. The point is to create a stable strategic loop, not a giant speculative planner.