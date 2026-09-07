# Middleware stack

Every request passes down this stack before routing, and back up it on the way
out. Order is declared in `config/settings/base.py` and is not arbitrary.

```mermaid
flowchart TD
    REQ(["HTTP request"]) --> SEC

    SEC["SecurityMiddleware<br/><i>HSTS, SSL redirect</i>"]
    CORS["CorsMiddleware<br/><i>answers preflight OPTIONS</i>"]
    SESS["SessionMiddleware"]
    COMMON["CommonMiddleware<br/><i>URL normalisation</i>"]
    CSRF["CsrfViewMiddleware"]
    AUTH["AuthenticationMiddleware<br/><i>sets request.user from session</i>"]
    APIAUTH["APIAuthenticationMiddleware<br/><b>apps/core/middleware.py</b><br/><i>resolves the Bearer token</i>"]
    CURUSER["CurrentUserMiddleware<br/><b>apps/core/current_user.py</b><br/><i>binds user to a contextvar</i>"]
    MSG["MessageMiddleware"]
    CLICK["XFrameOptionsMiddleware"]
    ALOG["AuditlogMiddleware<br/><i>records the actor for history</i>"]

    SEC --> CORS --> SESS --> COMMON --> CSRF --> AUTH --> APIAUTH --> CURUSER --> MSG --> CLICK --> ALOG
    ALOG --> URLCONF["URL resolution<br/><b>config/urls.py</b>"]
    URLCONF --> VIEW["View / ViewSet"]

    VIEW -.->|"response unwinds back up"| RESET["CurrentUserMiddleware<br/>resets the contextvar in <i>finally</i>"]
    RESET -.-> RESP(["HTTP response"])

    style REQ stroke:#4d90d9,stroke-width:2px
    style RESP stroke:#3fa860,stroke-width:2px
    style APIAUTH stroke:#d99a2b,stroke-width:2px
    style CURUSER stroke:#d99a2b,stroke-width:2px
    style RESET stroke:#d99a2b,stroke-width:2px
```

## Why the order matters

**`CorsMiddleware` sits second**, immediately after security. It has to answer a
preflight `OPTIONS` request before `CommonMiddleware` gets a chance to redirect
or rewrite it. Placed lower, preflights fail in ways that surface in the browser
as an opaque CORS error with no server-side trace.

**`APIAuthenticationMiddleware` exists because DRF authenticates too late.**
DRF resolves the token inside the view, during `dispatch()`. Both middlewares
below it read `request.user`, and would otherwise see `AnonymousUser` on every
token-authenticated request:

```mermaid
flowchart LR
    subgraph without["Without it"]
        direction TB
        W1["AuthenticationMiddleware<br/>request.user = AnonymousUser"]
        W2["CurrentUserMiddleware<br/>contextvar = None"]
        W3["AuditlogMiddleware<br/>actor = None"]
        W4["View: DRF authenticates<br/><i>too late</i>"]
        W5["created_by = NULL<br/>audit actor = 'System'"]
        W1 --> W2 --> W3 --> W4 --> W5
    end

    subgraph with["With it"]
        direction TB
        C1["AuthenticationMiddleware<br/>request.user = AnonymousUser"]
        C2["APIAuthenticationMiddleware<br/>decodes Bearer, sets request.user"]
        C3["CurrentUserMiddleware<br/>contextvar = real user"]
        C4["AuditlogMiddleware<br/>actor = real user"]
        C5["created_by = user<br/>audit actor = user"]
        C1 --> C2 --> C3 --> C4 --> C5
    end

    style W5 stroke:#d9534f,stroke-width:2px
    style C5 stroke:#3fa860,stroke-width:2px
    style C2 stroke:#d99a2b,stroke-width:2px
```

An invalid token is swallowed there deliberately — DRF authenticates again in
the view and owns turning a bad token into a properly shaped 401.

**`CurrentUserMiddleware` resets in a `finally` block.** Without the reset, a
reused worker thread would leak the previous request's user into the next one,
stamping `created_by` with the wrong person.
