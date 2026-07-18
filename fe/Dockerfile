# ---- Frontend image: Vite/React build served by nginx ----
FROM node:22-alpine AS build
WORKDIR /app

# Same-origin API: nginx proxies /auth /chat /catalog /health to the backend,
# so the app is built with an empty VITE_API_BASE_URL (relative paths).
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
