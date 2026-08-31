from app.infrastructure.database.models import RoleName

# Permission catalog
CUSTOMERS_READ = "customers.read"
CUSTOMERS_WRITE = "customers.write"
CONVERSATIONS_READ = "conversations.read"
CONVERSATIONS_WRITE = "conversations.write"
CONVERSATIONS_ASSIGN = "conversations.assign"
TICKETS_READ = "tickets.read"
TICKETS_WRITE = "tickets.write"
USERS_READ = "users.read"
USERS_WRITE = "users.write"
TEAMS_READ = "teams.read"
TEAMS_WRITE = "teams.write"
SETTINGS_READ = "settings.read"
SETTINGS_WRITE = "settings.write"
KNOWLEDGE_READ = "knowledge.read"
KNOWLEDGE_WRITE = "knowledge.write"
AI_READ = "ai.read"
AI_WRITE = "ai.write"

ALL_PERMISSIONS = [
    CUSTOMERS_READ,
    CUSTOMERS_WRITE,
    CONVERSATIONS_READ,
    CONVERSATIONS_WRITE,
    CONVERSATIONS_ASSIGN,
    TICKETS_READ,
    TICKETS_WRITE,
    USERS_READ,
    USERS_WRITE,
    TEAMS_READ,
    TEAMS_WRITE,
    SETTINGS_READ,
    SETTINGS_WRITE,
    KNOWLEDGE_READ,
    KNOWLEDGE_WRITE,
    AI_READ,
    AI_WRITE,
]

ROLE_PERMISSIONS: dict[RoleName, list[str]] = {
    RoleName.OWNER: list(ALL_PERMISSIONS),
    RoleName.ADMIN: list(ALL_PERMISSIONS),
    RoleName.MANAGER: [
        CUSTOMERS_READ,
        CUSTOMERS_WRITE,
        CONVERSATIONS_READ,
        CONVERSATIONS_WRITE,
        CONVERSATIONS_ASSIGN,
        TICKETS_READ,
        TICKETS_WRITE,
        USERS_READ,
        TEAMS_READ,
        TEAMS_WRITE,
        SETTINGS_READ,
        KNOWLEDGE_READ,
        KNOWLEDGE_WRITE,
        AI_READ,
        AI_WRITE,
    ],
    RoleName.AGENT: [
        CUSTOMERS_READ,
        CUSTOMERS_WRITE,
        CONVERSATIONS_READ,
        CONVERSATIONS_WRITE,
        CONVERSATIONS_ASSIGN,
        TICKETS_READ,
        TICKETS_WRITE,
        USERS_READ,
        TEAMS_READ,
        KNOWLEDGE_READ,
        KNOWLEDGE_WRITE,
        AI_READ,
        AI_WRITE,
    ],
    RoleName.READ_ONLY: [
        CUSTOMERS_READ,
        CONVERSATIONS_READ,
        TICKETS_READ,
        USERS_READ,
        TEAMS_READ,
        SETTINGS_READ,
        KNOWLEDGE_READ,
        AI_READ,
    ],
}
