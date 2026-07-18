# DMX Advisor frontend

## Run locally

Start BE1 on port `8100`, then:

```bash
cd fe
npm install
npm run dev
```

During local development, the browser calls `/auth`, `/chat`, and `/health`
on the Vite origin. Vite proxies those requests to BE1 at
`http://127.0.0.1:8100`. This avoids hostname, CORS, and `SameSite` cookie
mismatches when Vite is opened through localhost, a LAN address, or a remote
development URL.

To change the local proxy target, copy `.env.example` to `.env` and set:

```dotenv
VITE_DEV_PROXY_TARGET=http://127.0.0.1:8100
```

For a production build that calls a separate backend origin, set
`VITE_API_BASE_URL`. That frontend origin must also be listed in BE1's
`FRONTEND_ORIGINS`.

## Authentication

- `/login`: phone and password login.
- `/register`: phone, password, and confirmation registration.
- Registration signs the new user in immediately.
- `AuthProvider` restores `/auth/me` at startup and performs one refresh retry.
- JWTs stay in backend-issued HttpOnly cookies and are never stored by React.
- The header shows the masked phone and logout menu for authenticated users.

## User-owned chat sessions

- Guests can open chat without signing in. Their messages remain visible in
  the current widget only; each backend turn is stateless and is not saved.
- The browser creates a conversation with `POST /chat/sessions` before sending
  the first message for an authenticated user.
- Messages stream from `POST /chat/sessions/{id}/messages`.
- Guest messages stream from `POST /chat/guest/messages` without a session ID.
- React receives only the server-generated public session UUID. BE1 keeps the
  LangGraph thread ID private and checks the session owner on every request.
- `src/lib/chatApi.js` also exposes list, read, rename, and delete helpers for a
  future conversation-history screen.

## Validation

```bash
npm test
npm run lint
npm run build
```
