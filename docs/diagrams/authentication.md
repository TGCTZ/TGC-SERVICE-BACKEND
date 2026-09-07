# Authentication

JWT via `djangorestframework-simplejwt`, with rotation and blacklisting on.

## Token lifecycle

```mermaid
flowchart LR
    LOGIN["POST /auth/login/"] --> PAIR["access — 60 min<br/>refresh — 14 days"]
    PAIR --> USE["Authorization: Bearer access"]
    USE --> EXPIRED{"access expired?"}
    EXPIRED -->|no| SERVED["request served"]
    EXPIRED -->|yes| REFRESH["POST /auth/refresh/"]

    REFRESH --> ROTATE["new pair issued<br/>old refresh blacklisted"]
    ROTATE --> USE

    USE --> LOGOUT["POST /auth/logout/"]
    LOGOUT --> BL[("refresh blacklisted")]

    style LOGIN stroke:#4d90d9,stroke-width:2px
    style SERVED stroke:#3fa860,stroke-width:2px
    style EXPIRED stroke:#d99a2b,stroke-width:2px
    style BL stroke:#d9534f,stroke-width:2px
```

## Login

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant V as LoginView
    participant S as LoginSerializer
    participant DB as Database
    participant A as auth service

    C->>V: POST /auth/login/ {email, password}
    Note over V: throttle_scope "auth" — 6 per minute
    V->>S: validate()
    S->>DB: authenticate via default manager
    Note over DB: the manager excludes soft-deleted users,<br/>so a deleted account cannot log in
    alt credentials bad or user inactive
        DB-->>S: no user
        S-->>C: 401 Unauthorized
    else valid
        DB-->>S: user
        S->>S: mint access + refresh,<br/>embed email and full_name claims
        S-->>V: access, refresh, user
        V->>A: record_login(user)
        A->>DB: UPDATE last_login_at
        V-->>C: 200 with access, refresh, user + permissions
    end
```

The response embeds the serialised user **and their permission list**, which
saves the client an immediate follow-up call to `/auth/me/` just to render a
name and decide which nav items to show.

## Refresh with rotation

```mermaid
flowchart TD
    REQ(["POST /auth/refresh/"]) --> CHECK{"token valid<br/>and not blacklisted?"}
    CHECK -->|no| E401(["401<br/>token invalid or expired"])
    CHECK -->|yes| NEW["issue new access + refresh"]
    NEW --> BLACK["ROTATE_REFRESH_TOKENS<br/>+ BLACKLIST_AFTER_ROTATION<br/>blacklist the one just used"]
    BLACK --> OK(["200 with new pair"])

    style REQ stroke:#4d90d9,stroke-width:2px
    style CHECK stroke:#d99a2b,stroke-width:2px
    style OK stroke:#3fa860,stroke-width:2px
    style E401 stroke:#d9534f,stroke-width:2px
```

Each refresh token is single-use. A replayed one is already blacklisted, which
is how a stolen refresh token gets detected rather than silently reused.

## Password change and session revocation

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant V as ChangePasswordView
    participant S as change_password service
    participant DB as Database

    C->>V: POST /auth/password/
    V->>S: change_password(...)
    S->>S: user.check_password(current)
    alt current password wrong
        S-->>C: 400 ServiceError
    else new password equals current
        S-->>C: 400 ServiceError
    else ok
        S->>DB: set_password + save
        S->>DB: blacklist every OutstandingToken
        Note over DB: a stolen session cannot outlive<br/>the password change meant to end it
        S-->>C: 204 No Content
    end
```

## Logout

```mermaid
flowchart TD
    REQ(["POST /auth/logout/"]) --> VALID{"refresh token<br/>parses?"}
    VALID -->|"expired or already blacklisted"| SUPPRESS["contextlib.suppress(TokenError)<br/><i>the session is already over,<br/>which is what was asked for</i>"]
    VALID -->|yes| BL[("blacklist it")]
    SUPPRESS --> OK(["205 Reset Content"])
    BL --> OK

    style REQ stroke:#4d90d9,stroke-width:2px
    style VALID stroke:#d99a2b,stroke-width:2px
    style OK stroke:#3fa860,stroke-width:2px
```

## The revocation gap

Blacklisting acts on **refresh** tokens. An already-issued **access** token
stays valid until it expires:

```mermaid
flowchart LR
    PW["Password changed at T"] --> RT["refresh tokens<br/>revoked immediately"]
    PW --> AT["access token still valid<br/>until T + 60 minutes"]

    style RT stroke:#3fa860,stroke-width:2px
    style AT stroke:#d9534f,stroke-width:2px
```

`JWT_ACCESS_MINUTES` **is** that exposure window — a security parameter, not a
performance knob. Shorten it where an immediate lockout matters; the cost is
more refresh round-trips.
