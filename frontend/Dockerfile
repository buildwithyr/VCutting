# Frontend: Vite-Build, ausgeliefert von nginx
FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Im Container laeuft das Frontend hinter nginx, das /api an das Backend
# weiterreicht. Deshalb bleibt die Basis-URL relativ.
ENV VITE_API_BASE_URL=/api
RUN npm run build


FROM nginx:1.27-alpine AS runtime

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget --quiet --spider http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
