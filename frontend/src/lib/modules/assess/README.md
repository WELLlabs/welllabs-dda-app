# Assess module (frontend)

ODK Central-backed monitoring UI.

| Piece | Role |
|-------|------|
| `api.js` | Client for `/api/assess` (import projects, forms, submissions) |
| `components/AssessProjects.svelte` | List + import/refresh ODK projects |
| `components/AssessForms.svelte` | Forms for the active project |
| `components/AssessSubmissions.svelte` | Submission list and detail |

Wired from `routes/(protected)/assess/+page.svelte` as a simple projects → forms → submissions flow.
