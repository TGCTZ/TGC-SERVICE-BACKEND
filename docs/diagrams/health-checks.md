# Health checks

Two probes at `/api/health/` and `/api/health/ready/`, mounted **outside** the
`/api/v1/` prefix so a version bump cannot break your infrastructure.

## Liveness versus readiness

```mermaid
flowchart TD
    subgraph live["GET /api/health/ — liveness"]
        direction TB
        L1["no authentication<br/>no throttling"]
        L2["touches nothing external"]
        L3(["200 with status ok"])
        L1 --> L2 --> L3
    end

    subgraph ready["GET /api/health/ready/ — readiness"]
        direction TB
        R1["no authentication<br/>no throttling"]
        R2["SELECT 1"]
        R3["migration plan empty?"]
        R4{"all checks ok?"}
        R5(["200 status ok"])
        R6(["503 status degraded"])
        R1 --> R2 --> R3 --> R4
        R4 -->|yes| R5
        R4 -->|no| R6
    end

    style L3 stroke:#3fa860,stroke-width:2px
    style R4 stroke:#d99a2b,stroke-width:2px
    style R5 stroke:#3fa860,stroke-width:2px
    style R6 stroke:#d9534f,stroke-width:2px
```

## Why they are separate

```mermaid
flowchart LR
    OUTAGE["Database goes down"] --> LIVEP["Liveness: still 200<br/><i>the process is fine</i>"]
    OUTAGE --> READYP["Readiness: 503<br/><i>cannot serve traffic</i>"]

    LIVEP --> KEEP["orchestrator keeps<br/>the container running"]
    READYP --> DRAIN["load balancer stops<br/>sending it requests"]

    KEEP --> RECOVER["when the database returns,<br/>readiness passes and traffic resumes"]
    DRAIN --> RECOVER

    style OUTAGE stroke:#4d90d9,stroke-width:2px
    style LIVEP stroke:#3fa860,stroke-width:2px
    style READYP stroke:#d99a2b,stroke-width:2px
    style RECOVER stroke:#3fa860,stroke-width:2px
```

A liveness probe that queried the database would fail during any outage, and the
orchestrator would respond by **restarting healthy containers** — turning a
recoverable dependency blip into a restart storm. Keeping liveness dependency-free
is the whole point of having two endpoints.

## Readiness checks

```mermaid
flowchart TD
    REQ(["GET /api/health/ready/"]) --> DB

    DB["_check_database()<br/>cursor.execute('SELECT 1')"]
    DB -->|raises| DBERR["database: error: OperationalError"]
    DB -->|ok| DBOK["database: ok"]

    DBOK --> MIG
    DBERR --> MIG

    MIG["_check_migrations()<br/>MigrationExecutor.migration_plan()"]
    MIG -->|"plan not empty"| MIGPEND["migrations: N unapplied"]
    MIG -->|"plan empty"| MIGOK["migrations: ok"]

    MIGOK --> AGG
    MIGPEND --> AGG

    AGG{"every check == ok?"}
    AGG -->|yes| OK(["200<br/>status ok, checks {...}"])
    AGG -->|no| BAD(["503<br/>status degraded, checks {...}"])

    style REQ stroke:#4d90d9,stroke-width:2px
    style AGG stroke:#d99a2b,stroke-width:2px
    style OK stroke:#3fa860,stroke-width:2px
    style BAD stroke:#d9534f,stroke-width:2px
```

The migration check catches the deploy that starts a container against a
half-migrated schema — a failure that otherwise surfaces as scattered
`ProgrammingError`s on unrelated endpoints, hours later.

The response names **which** check failed rather than returning a bare 503, so
the on-call reader knows whether to look at the database or the deploy pipeline.

## Deliberate 503, not 500

An exception inside a probe would produce a 500, which reads as an application
bug and, on some load balancers, still routes traffic. A 503 is the documented
signal for "temporarily unable to serve", and is what makes a rolling deploy
hold back.
