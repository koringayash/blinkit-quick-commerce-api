<!-- LOVABLE:BEGIN -->
> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.
<!-- LOVABLE:END -->

## Architecture
- Frontend only: all data comes from the user's external FastAPI backend (repo koringayash/blinkit-quick-commerce-api) via `src/lib/api.ts`; never reimplement backend logic here.
- API base URL is user-configurable (Settings dialog, stored in localStorage, default http://localhost:8000) because the backend is not deployed yet.
- Auth uses the backend's bearer token stored in localStorage, exposed through `src/lib/session.tsx`.
