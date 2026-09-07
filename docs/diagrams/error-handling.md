# Error handling

`apps/core/handlers.py` is the single funnel every exception passes through.
It is wired in as `EXCEPTION_HANDLER`, so no view has to shape its own errors.

## The funnel

```mermaid
flowchart TD
    EXC(["exception raised anywhere<br/>in a DRF view"]) --> TYPE{"what type?"}

    TYPE -->|ServiceError| SE["convert to DRF ValidationError<br/>detail: str(exc)"]
    TYPE -->|"Django ValidationError"| DVE["convert, using message_dict<br/>when the model provided one"]
    TYPE -->|Http404| H404["convert to NotFound"]
    TYPE -->|IntegrityError| IE["log a warning, then convert<br/>to a generic conflict message"]
    TYPE -->|anything else| PASS["pass through untouched"]

    SE --> DRF
    DVE --> DRF
    H404 --> DRF
    IE --> DRF
    PASS --> DRF

    DRF["drf_exception_handler()"]
    DRF --> KNOWN{"did DRF recognise it?"}
    KNOWN -->|yes| SHAPED(["shaped response<br/>400 / 401 / 403 / 404 / 429"])
    KNOWN -->|no| LOG["logger.exception()<br/><i>full traceback to the log</i>"]
    LOG --> R500(["500<br/>detail: A server error occurred."])

    style EXC stroke:#4d90d9,stroke-width:2px
    style TYPE stroke:#d99a2b,stroke-width:2px
    style KNOWN stroke:#d99a2b,stroke-width:2px
    style SHAPED stroke:#3fa860,stroke-width:2px
    style R500 stroke:#d9534f,stroke-width:2px
```

The 500 branch is the important one. An unrecognised exception is logged **in
full**, with its traceback, and reported to the client as a bare sentence.
Internals — table names, file paths, SQL fragments — never reach the caller.

## Status code map

| Raised | Status | Body |
| --- | --- | --- |
| `ServiceError` | 400 | `{"detail": "..."}` |
| Django `ValidationError` | 400 | field-keyed |
| Serializer validation | 400 | field-keyed |
| Not authenticated | 401 | `{"detail": "..."}` |
| Permission denied | 403 | `{"detail": "..."}` |
| `Http404` / missing object | 404 | `{"detail": "Not found."}` |
| `IntegrityError` | 400 | generic conflict message, warning logged |
| Throttled | 429 | `{"detail": "..."}` |
| Anything unhandled | 500 | generic message, traceback logged |

## Why services raise rather than return

```mermaid
flowchart LR
    subgraph bad["Returning error codes"]
        direction TB
        B1["service returns (ok, error)"]
        B2["every caller must check"]
        B3["one forgotten check<br/>= silent corruption"]
        B1 --> B2 --> B3
    end

    subgraph good["Raising ServiceError"]
        direction TB
        G1["service raises"]
        G2["transaction rolls back"]
        G3["handler shapes the response"]
        G4["impossible to ignore"]
        G1 --> G2 --> G3 --> G4
    end

    style B3 stroke:#d9534f,stroke-width:2px
    style G4 stroke:#3fa860,stroke-width:2px
```

`ServiceError` carries no HTTP knowledge, so the same service works unchanged
from a management command, a webhook or a test.

## Transaction interaction

`ATOMIC_REQUESTS = True` wraps every request in a transaction.

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant TX as Transaction
    participant V as View
    participant S as Service
    participant DB as Database

    C->>TX: POST request
    TX->>V: begin
    V->>S: call
    S->>DB: write A
    S->>DB: write B
    S--xV: ServiceError on rule C
    V->>TX: exception propagates
    TX->>DB: ROLLBACK
    Note over DB: writes A and B are both undone —<br/>no half-finished state survives
    TX-->>C: 400 from the handler
```

This is why services that write more than one row do not need their own
`try`/`except` cleanup: a raised exception unwinds the whole request.
