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

# Only the built artifacts are needed at runtime. node_modules is intentionally
# omitted — `npx serve` fetches its own tiny runtime, and devDependencies
# (eslint, vitest, playwright, testing-library, …) must not ship in the image.
COPY --from=builder /app/frontend/dist ./dist
COPY --from=builder /app/frontend/package.json ./

EXPOSE 5173

CMD ["npx", "serve", "dist", "-l", "5173", "--no-clipboard"]
