# Billing service on-call runbook

## Deploy and rollback
The service deploys from the `billing` pipeline. To roll back, run:

```
kubectl -n billing rollout undo deployment/billing rollback --to-revision=0
```

The rollback has a **300** second timeout. If it times out, the previous revision stays live and you escalate.

## Escalation
If the service is down for more than **15 minutes**, page the **payments** team's **on-call** engineer and open an incident channel. Do not page the platform team first: the billing service runs on its own cluster.

## Database
The service connects to the primary database through a sidecar proxy. The proxy pool is sized at 40 connections per replica. The database vendor and version are recorded in the platform inventory, not in this runbook.
