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

## Validation

```bash
npm test
npm run lint
npm run build
```
