# Write request

`POST /api/v1/customers/` — and the service-layer variant beneath it.

```mermaid
flowchart TD
    REQ(["POST /api/v1/customers/<br/>JSON body"]) --> MW["Middleware stack"]
    MW --> TX[["ATOMIC_REQUESTS opens<br/>a transaction"]]
    TX --> GATES{"Authentication<br/>Permissions: add_customer<br/>Throttling"}
    GATES -->|any fail| ERRGATE["401 / 403 / 429"]
    GATES -->|pass| VALID

    VALID{"CustomerSerializer<br/>is_valid()"}
    VALID -->|invalid| E400["400<br/>field-keyed errors"]
    VALID -->|valid| SAVE

    SAVE["perform_create()<br/>serializer.save()"]
    SAVE --> MODEL["Customer.save()<br/><b>BaseModel.save()</b>"]
    MODEL --> STAMP["reads contextvar<br/>stamps created_by / updated_by"]
    STAMP --> INSERT[("INSERT")]
    INSERT --> SIGNAL["auditlog post_save signal"]
    SIGNAL --> LOG[("LogEntry<br/>field-level diff")]
    LOG --> COMMIT[["transaction commits"]]
    COMMIT --> OK(["201 Created<br/>serialised customer"])

    style REQ stroke:#4d90d9,stroke-width:2px
    style OK stroke:#3fa860,stroke-width:2px
    style VALID stroke:#d99a2b,stroke-width:2px
    style GATES stroke:#d99a2b,stroke-width:2px
    style E400 stroke:#d9534f,stroke-width:2px
    style ERRGATE stroke:#d9534f,stroke-width:2px
```

## When a service is involved

Anything spanning more than one model, or carrying a business rule, goes through
`apps/<app>/services/`. Services know nothing about HTTP — they raise
`ServiceError`, and one handler maps it to a status code.

```mermaid
flowchart TD
    VIEW["View<br/><i>thin: gates + delegation</i>"] --> SERVICE["Service function<br/>keyword-only args<br/>@transaction.atomic"]

    SERVICE --> RULE{"business rule<br/>satisfied?"}
    RULE -->|no| RAISE["raise ServiceError"]
    RULE -->|yes| WORK["model writes"]

    RAISE --> HANDLER["api_exception_handler<br/><b>apps/core/handlers.py</b>"]
    HANDLER --> R400(["400<br/>detail: message"])

    WORK --> ROLLBACK{"any exception?"}
    ROLLBACK -->|yes| RB[["transaction rolls back<br/><i>no partial write survives</i>"]]
    ROLLBACK -->|no| R200(["200 / 201"])

    style VIEW stroke:#4d90d9,stroke-width:2px
    style RULE stroke:#d99a2b,stroke-width:2px
    style ROLLBACK stroke:#d99a2b,stroke-width:2px
    style R200 stroke:#3fa860,stroke-width:2px
    style R400 stroke:#d9534f,stroke-width:2px
    style RB stroke:#d9534f,stroke-width:2px
```

## Where the actor comes from

`BaseModel.save()` never receives the request user as an argument. It reads the
contextvar that `CurrentUserMiddleware` set, which is what keeps the model layer
free of any HTTP knowledge.

One subtlety worth knowing: when a caller passes `update_fields`, the stamped
columns are **added to that set**. A naive implementation computes `updated_by`
and then hands Django an `update_fields` list that excludes it — the value is
calculated and then silently discarded. `test_partial_save_still_stamps_the_actor`
guards exactly that.
