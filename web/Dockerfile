# Web image: builds the React app, serves it with nginx and forwards /api and /ws to the backend.
# NOT built or run yet - see README.
FROM node:22-alpine AS build
WORKDIR /web
COPY package.json package-lock.json ./
# No install scripts: none of the packages this build uses needs one (only fsevents has one, and it is macOS only).
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build

# The unprivileged nginx image runs as the nginx user, not root, so it listens on 8080 instead of 80.
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 8080
