# Settings and Collaboration

The Settings area is the main place for account management, organization-based sharing, and connector setup.

## Accessing Settings

Open the Settings screen at `/settings` from the protected app shell. It contains three tabs:

- **Account** — shows the signed-in profile details.
- **Organizations** — create and manage organizations, invite members, and view shared projects.
- **Connectors** — connect personal QField Cloud credentials for packaging and syncing.

## Account

The Account page shows the current user’s name and email from the session. It is a lightweight profile view used to confirm which account is active before working in Diagnose or Assess.

## Organizations

Organizations let teams share diagnosis projects without granting access one user at a time.

### Create and manage organizations

- Create a new organization from the Organizations tab.
- Organization admins can add members by email.
- Admins can promote or demote other members.
- Any member can leave an organization.
- Only admins can delete an organization.

### Shared projects

When a diagnosis project is shared with an organization, every member of that organization gains access to the project. The Organizations tab also lists projects currently shared with each organization.

## Connectors

The Connectors screen stores personal integration credentials for downstream workflows.

### QField Cloud

Users can connect their own QField Cloud account to:

- package diagnoses for mobile use
- sync field updates back into the platform
- reuse the connected account’s token for package uploads and sync operations

The app stores the username, token, and expiration timestamp on the `users` row. If the token expires, the UI shows a reconnect state.

### ODK Central

ODK credentials are also stored on the `users` row for Assess workflows. The server-side connector endpoints exist, but the current UI does not expose a full ODK connector form yet. In practice, server-side sync still relies on environment variables such as `ODK_BASE_URL`, `ODK_USERNAME`, and `ODK_PASSWORD`.

## Related backend endpoints

The Settings UI uses the Accounts API endpoints under `/api/accounts`:

- Auth: register, login, logout, current user
- Users: email lookup for invites and sharing
- Organizations: create/list/delete orgs and manage members
- QField: connect, status, disconnect
- ODK: connector status and credential storage endpoints

See [api.md](api.md) for the full endpoint reference.
