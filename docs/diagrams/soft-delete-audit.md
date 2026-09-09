# Soft delete and audit

Rows are never physically removed by ordinary code paths. `delete()` stamps
`deleted_at` instead.

## Delete and restore

```mermaid
flowchart TD
    DEL(["DELETE /api/v1/customers/1/"]) --> PERM{"has delete_customer?"}
    PERM -->|no| E403(["403"])
    PERM -->|yes| SOFT["perform_destroy()<br/>instance.delete()"]

    SOFT --> STAMP["BaseModel.delete()<br/>deleted_at = now<br/>deleted_by = current user"]
    STAMP --> UPD[("UPDATE — the row survives")]
    UPD --> COMP["_log(DELETE)<br/><i>explicit LogEntry</i>"]
    COMP --> R204(["204 No Content"])

    UPD --> HIDDEN["hidden from the default manager,<br/>so list views no longer return it"]

    RES(["POST /api/v1/customers/1/restore/"]) --> FIND["get_queryset() forces<br/>only_trashed for this action"]
    FIND --> ISDEL{"actually deleted?"}
    ISDEL -->|no| E400(["400<br/>this record is not deleted"])
    ISDEL -->|yes| CLEAR["restore()<br/>deleted_at = NULL<br/>deleted_by = NULL"]
    CLEAR --> COMP2["_log(UPDATE, restored=True)"]
    COMP2 --> R200(["200 with the restored object"])

    style DEL stroke:#4d90d9,stroke-width:2px
    style RES stroke:#4d90d9,stroke-width:2px
    style PERM stroke:#d99a2b,stroke-width:2px
    style ISDEL stroke:#d99a2b,stroke-width:2px
    style R204 stroke:#3fa860,stroke-width:2px
    style R200 stroke:#3fa860,stroke-width:2px
    style E403 stroke:#d9534f,stroke-width:2px
    style E400 stroke:#d9534f,stroke-width:2px
```

The restore action forces `only_trashed`, because the row it needs to find is
one that every other view deliberately hides.

## Why an explicit log entry is needed

```mermaid
flowchart LR
    SD["Soft delete"] --> SQL[("UPDATE orders_customer<br/>SET deleted_at = now")]
    SQL --> AL["django-auditlog sees<br/>an ordinary UPDATE"]
    AL --> INDIST["indistinguishable from<br/>any other field change"]
    INDIST --> FIX["SoftDeleteViewSetMixin._log()<br/>writes an explicit DELETE entry"]
    FIX --> GOOD["history shows a deletion"]

    style SD stroke:#4d90d9,stroke-width:2px
    style INDIST stroke:#d9534f,stroke-width:2px
    style FIX stroke:#d99a2b,stroke-width:2px
    style GOOD stroke:#3fa860,stroke-width:2px
```

This is the cost of pairing a custom soft delete with an off-the-shelf audit
library. Nothing was physically deleted, so `post_delete` never fires.

## Manager selection

```mermaid
flowchart TD
    MODEL["A BaseModel subclass"] --> DEFAULT["objects — SoftDeleteManager<br/><i>default: live rows only</i>"]
    MODEL --> ALL["all_objects — plain Manager<br/><i>includes deleted rows</i>"]

    DEFAULT --> USED["every list view, every FK lookup,<br/>authentication"]
    ALL --> ADMIN["Django admin, audit views,<br/>the restore action"]

    style MODEL stroke:#4d90d9,stroke-width:2px
    style DEFAULT stroke:#3fa860,stroke-width:2px
    style ALL stroke:#d99a2b,stroke-width:2px
```

Because `objects` is the **default** manager, a soft-deleted user cannot
authenticate — the login lookup simply does not find them. That falls out of the
manager choice rather than needing its own check.

## Partial unique constraints

```mermaid
flowchart TD
    Q["Species 'Corundum' is soft-deleted.<br/>Can a new 'Corundum' be created?"] --> WHICH{"constraint style"}

    WHICH -->|"unique=True"| BAD["IntegrityError<br/><i>the deleted row holds the<br/>name hostage forever</i>"]
    WHICH -->|"UniqueConstraint with<br/>condition deleted_at IS NULL"| GOOD["created successfully"]

    style Q stroke:#4d90d9,stroke-width:2px
    style WHICH stroke:#d99a2b,stroke-width:2px
    style BAD stroke:#d9534f,stroke-width:2px
    style GOOD stroke:#3fa860,stroke-width:2px
```

Every natural key in the project uses the partial form — `name` on
`ReferenceModel`, plus `reference_number`, `bill_number`, `trx_id` and the
certificate's number and token. A plain
`unique=True` on a soft-deletable model is a bug waiting to be filed as "cannot
create, says it already exists, but I deleted it".

## What lands in the audit trail

```mermaid
flowchart LR
    SAVE["model.save()"] --> SIG["auditlog post_save"]
    SIG --> DIFF["field-level diff,<br/>changed fields only"]
    DIFF --> EXCL["excluded: created_at, updated_at,<br/>created_by, updated_by, deleted_by"]
    EXCL --> ENTRY[("LogEntry<br/>actor, action, changes, remote_addr")]
    ENTRY --> API["GET /api/v1/activity-logs/<br/><i>read-only</i>"]

    style SAVE stroke:#4d90d9,stroke-width:2px
    style ENTRY stroke:#3fa860,stroke-width:2px
```

Registration is automatic: `apps/core/audit.py` walks the app registry and
registers every concrete `BaseModel` subclass, so a new model is audited the
moment it inherits the base. `deleted_at` stays tracked — it is the field that
makes soft deletes visible in the history at all.

The activity-log API is read-only by design. An audit trail that can be edited
is not an audit trail.
