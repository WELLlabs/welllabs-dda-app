# Settings and Collaboration

The Settings area is the main place for account management, organization-based sharing, and connector setup.

## Accessing Settings

Open the Settings screen at `/settings` from the protected app shell. It contains three tabs:

- **Account** — shows the signed-in profile details.
- **Organizations** — create and manage organizations, invite members, and view shared projects.
- **Connectors** — connect personal QField Cloud credentials for packaging and syncing.

## Account

The Account page shows the current user’s name and email from the session. After the first
Google sign-up, `/complete-profile` asks you to confirm a display name before entering the app.

QField Cloud credentials are stored in `user_qfield_credentials`, not on the `users` row.

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

The app stores the username, token, and expiration timestamp in `user_qfield_credentials`. If the token expires, the UI shows a reconnect state.

### ODK Central

Assess uses **server-side** ODK Central credentials from environment variables
(`ODK_BASE_URL`, `ODK_USERNAME`, `ODK_PASSWORD`). Per-user ODK columns on `users` were removed.

## Related backend endpoints

The Settings UI uses the Accounts API endpoints under `/api/accounts`:

- Auth: register, login, logout, verify, reset, Google OAuth, current user, profile update
- Users: email lookup for invites and sharing
- Organizations: create/list/delete orgs and manage members
- QField: connect, status, disconnect (`user_qfield_credentials`)

See [api.md](api.md) and [auth.md](auth.md).
