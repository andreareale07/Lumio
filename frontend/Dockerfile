FROM node:20-alpine AS build
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .
ARG VITE_APP_NAME
ARG VITE_APP_TAGLINE
ENV VITE_APP_NAME=${VITE_APP_NAME} \
    VITE_APP_TAGLINE=${VITE_APP_TAGLINE}
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
