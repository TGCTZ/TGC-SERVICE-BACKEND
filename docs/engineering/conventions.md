# Conventions

Numbered so other files can cite them. `pyproject.toml` and
`.pre-commit-config.yaml` reference these numbers in their comments, which keeps
the tooling and the prose honest about each other.

## 1. Layering

Apps are ordered by dependency layer in `INSTALLED_APPS`, annotated `L1`-`L3`.
Imports point downward only. Two apps in the same layer must not import each
other's models; shared data moves down into `apps.core`.

## 2. Views are thin

A view resolves permissions, builds a queryset and delegates. Anything that
spans more than one model, or has a rule attached to it, belongs in a service.

## 3. Services

Module-level functions, not classes. Keyword-only arguments after the subject.
Decorated with `@transaction.atomic` when they write more than one row. They
raise `ServiceError` and know nothing about HTTP - the exception handler in
`apps.core.handlers` is the single place that maps them onto a status code.

## 4. Serializers validate and represent

They do not orchestrate. A serializer that needs to touch three models is a
service wearing a disguise.

## 5. Naming

`snake_case` for functions and fields, `PascalCase` for classes,
`SCREAMING_SNAKE_CASE` for module constants. Boolean fields read as assertions:
`is_active`, `requires_shipping`. Enforced by ruff's `N` rules.

## 6. Every model inherits `BaseModel`

That is what supplies soft delete, the audit columns and automatic actor
stamping. A model that genuinely must be hard-deleted is the exception and
should say why in its docstring.

## 7. Natural keys use partial unique constraints

Never a bare `unique=True` on a soft-deletable model. Use:

```python
models.UniqueConstraint(
    fields=["name"],
    condition=Q(deleted_at__isnull=True),
    name="%(app_label)s_%(class)s_unique_name",
)
```

Without the condition, a soft-deleted row holds its name hostage forever and
the value can never be reused.

## 8. Querysets are explicit about their joins

Every list view declares `select_related` for its to-one links and
`prefetch_related` for its to-many ones. Assert the query count in a test;
an N+1 is otherwise invisible until production.

## 9. No wildcard imports

Except in `config/settings/*`, where re-export is the whole point. Enforced by
ruff `F403`/`F405` with a per-file ignore for exactly that directory.

## 10. Permissions are declared, never defaulted

`DEFAULT_PERMISSION_CLASSES` is `IsAuthenticated`, so a view that forgets to
declare permissions fails closed. CRUD viewsets use `StrictModelPermissions`,
which - unlike DRF's stock class - also requires `view_<model>` for reads.

## 11. The role matrix lives in code

`apps/users/roles.py` holds `ROLE_PERMISSIONS`. Changes show up as a reviewable
diff, and `manage.py setup_roles` is idempotent, so any environment can be
brought back into line at any time.

## 12. Docstrings explain decisions

Every module, class and public function gets one. Say *why*, not *what*: the
code already says what. A docstring that restates the signature is noise.

## 13. Comments mark the non-obvious

A comment earns its place by explaining a constraint, a trade-off or a
surprising ordering. Comments that narrate readable code get deleted.

## 14. Secrets never have defaults

`SECRET_KEY` has no fallback: a missing value must crash on boot rather than
silently run on a guessable key. `DEBUG` defaults to `False`.

## 15. Tests use factories, not fixtures

`factory_boy` factories live in `apps/<app>/tests/factories.py` and are reused
by `seed`. One definition, two consumers. Lookup factories use
`django_get_or_create` so re-seeding is idempotent.

## 16. Test style

Module-level `pytestmark = pytest.mark.django_db`. Plain functions, no classes.
Plain `assert`. One behaviour per test, named for the behaviour.

## 17. Migrations are reviewed like code

Read the generated file before committing it. CI runs
`makemigrations --check --dry-run`, so a model change without a migration fails
the build.

## 18. Money is `DecimalField`

Never `FloatField`. Binary floating point accumulates rounding error that
eventually shows up on an invoice.

## 19. Imports are sorted into five groups

stdlib, third-party, django, first-party, local. Django gets its own section so
it reads as the framework rather than as one library among many. Enforced by
ruff's `I` rules with a custom `section-order`.

## 20. Paths use `pathlib`

Not `os.path`. Enforced by ruff `PTH`.

## 21. Reads that encode a gate live in `selectors.py`

A queryset that answers "what is waiting to be worked on" is a business rule, not
a view detail. The four worklists are aggregate or cross-app predicates that the
whitelist filter backend cannot express - `Count("stones") < F("stone_count")`,
`order__bill__status = PAID` - so a view holding one would put a rule where
nobody looks for it, and a second screen would soon hold a slightly different
copy.

```python
def findings_worklist():
    """Stones waiting for findings: bill settled, report not finalized."""
    return Stone.objects.filter(order__bill__status=BillStatus.PAID).exclude(
        report__is_finalized=True
    )
```

Exposed as `@action(detail=False)` on the ViewSet that already owns the model, so
pagination, `?search=` and `?ordering=` come for free.

## 22. Workflow verbs are actions, gated by `ActionPermissions`

A business action is a `POST` to its own route - `transition`, `finalize`,
`generate`, `revoke` - not a writable field. The field is read-only precisely so
the state cannot move without the service running and the trail being written.

`StrictModelPermissions` maps by HTTP method, so every `POST` would ask for
`add_<model>`. `ActionPermissions` lets the route name its own permission:

```python
class StoneViewSet(BaseModelViewSet, viewsets.ModelViewSet):
    action_permissions = {"transition": ["orders.transition_stone"]}
```

Without it the custom workflow permissions are decorative - anyone who can
register a stone could also certify one. An action that is not listed falls back
to the method map.

## 23. A query-count test must stamp the actor

`AuditFieldsMixin` renders `created_by` and `updated_by` as display labels, which
dereferences both foreign keys per row. `BaseModelViewSet` joins them, and
`apps/core/tests/test_audit_joins.py` guards that.

The trap is in the test, not the code: a factory creates rows **outside** a
request, so the actor columns are null, the label methods short-circuit, and the
N+1 is invisible. Create rows inside `set_current_user(...)` when the count is
what you are asserting.
