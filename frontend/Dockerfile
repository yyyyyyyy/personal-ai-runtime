FROM node:20-slim AS builder

ARG VITE_API_HOST=localhost
ARG VITE_API_PORT=8000
ENV VITE_API_HOST=${VITE_API_HOST}
ENV VITE_API_PORT=${VITE_API_PORT}

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ .
RUN npm run build

FROM node:20-slim

WORKDIR /app/frontend

COPY --from=builder /app/frontend/dist ./dist
COPY --from=builder /app/frontend/package.json ./
COPY --from=builder /app/frontend/vite.config.ts ./
COPY --from=builder /app/frontend/node_modules ./node_modules

EXPOSE 5173

CMD ["npx", "vite", "preview", "--host", "0.0.0.0", "--port", "5173"]
