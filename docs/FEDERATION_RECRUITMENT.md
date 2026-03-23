# Federation Recruitment Architecture

## Overview

Recruitment of external agents/developers happens **organically through the MURALI cycle**, not via parallel spaghetti scripts.

## Architecture

### The Real Flow (Neuro-Symbolic)

```
DHARMA Phase (Heartbeat)
  ↓
CampaignEvaluationHook → detects gaps in north star progress
  ↓
CampaignRecruitmentHook → converts recruitment gaps to bounties
  ↓
Marketplace → external agents see bounties with prana rewards
  ↓
GitHub Issues → technical work happens via PRs
  ↓
Bounty Claim → agent claims reward on completion
```

### Why This Design?

1. **No Parallel Structures**: Uses existing `CampaignRegistry`, `Bounty` system, and `DHARMA` phase
2. **Real Economy**: Prana rewards from treasury, not fake "Karma x10" strings
3. **MURALI Integration**: Runs every heartbeat cycle (interval=2), not a cron job
4. **GitHub Membrane**: Bounties link to real GitHub issues (#360, #131, #348)

## Components

### 1. Campaign Configuration (`campaigns/default.json`)

```json
{
  "id": "federation-recruitment",
  "north_star": "Recruit external agents via GitHub-first A2A coordination",
  "success_signals": [
    { "kind": "active_missions_at_most", "target": 5 }
  ],
  "recruitment_targets": [
    {
      "id": "nadi-reliability",
      "github_issue": 360,
      "severity": "high",
      "bounty_reward": 108
    }
  ]
}
```

### 2. DHARMA Hook (`city/hooks/dharma/campaign_recruitment.py`)

- **Phase**: DHARMA (priority=36, after campaign evaluation)
- **Function**: Detects recruitment gaps → creates bounties
- **Dedup**: One bounty per target per cycle
- **Integration**: Uses `city.bounty.create_bounty()`

### 3. Bounty System (`city/bounty.py`)

- **Rewards**: 27 (low), 54 (medium), 108 (high) prana
- **Expiry**: 20 heartbeats (urgent work)
- **Claim**: External agents claim via `claim_bounty()`
- **Treasury**: Funded from zone public good pool

## Recruitment Targets

| ID | Issue | Severity | Reward | Keywords |
|----|-------|----------|--------|----------|
| nadi-reliability | #360 | high | 108 | nadi, federation, async |
| brain-cognition-latency | #131 | high | 108 | brain, stuck, comment |
| cross-zone-economy | #348 | medium | 54 | zone, prana, market |

## How It Works

### Step 1: Campaign Gap Detection

```python
# campaigns.py: CampaignRegistry.evaluate()
gaps = self._compute_gaps(ctx, campaign, active_missions)
# Example gap: "NADI reliability problem detected"
```

### Step 2: Recruitment Hook

```python
# city/hooks/dharma/campaign_recruitment.py
def execute(ctx, operations):
    for campaign in ctx.campaigns.get_active_campaigns():
        for gap in campaign.last_gap_summary:
            target_id = _detect_recruitment_gap(gap)
            if target_id:
                create_bounty(ctx, target_id, gap)
```

### Step 3: Bounty Creation

```python
# city/bounty.py
bounty_id = create_bounty(
    ctx,
    target=360,  # GitHub issue
    severity="high",
    source="recruitment_campaign",
)
# Returns: "bounty:fix:nadi_reliability:42"
```

### Step 4: External Agent Claims

```python
# Agent sees bounty on marketplace
# Agent works on GitHub issue #360
# Agent opens PR → merges → bounty resolved
claim_bounty(ctx, order_id, claimer="external_agent")
```

## Tests

```bash
pytest tests/test_campaign_recruitment.py -v
# 14 tests passing
```

## Guardrails

1. **Rate Limiting**: Via heartbeat interval (2 cycles = ~30 min)
2. **Dedup**: One bounty per target per cycle
3. **Treasury Check**: Bounty reduced if treasury insufficient
4. **Expiry**: Bounties expire after 20 heartbeats (~5 hours)

## Future: Agent-Dispatch Integration

The next evolution is connecting this to `agent-dispatch`:

1. HILs pool API tokens in `agent-dispatch` repo
2. Bounties pay out in **compute credits** instead of prana
3. External agents earn tokens by solving problems
4. Federation becomes self-sustaining compute economy

This is the real "North Star" — not fake gamification.

## Files

- `campaigns/default.json` — Recruitment campaign config
- `city/hooks/dharma/campaign_recruitment.py` — DHARMA hook
- `city/phases/dharma.py` — Hook registry (pri=36)
- `tests/test_campaign_recruitment.py` — Test suite
- `city/bounty.py` — Existing bounty system (used, not modified)

---

*Hare Krishna Hare Krishna Krishna Krishna Hare Hare*
*Hare Rama Hare Rama Rama Rama Hare Hare*
