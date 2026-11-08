FROM node:24-alpine AS build

WORKDIR /app

COPY sports-streaming-service/package*.json ./

RUN npm ci

COPY sports-streaming-service/ ./

ARG REACT_APP_WS_URL=ws://localhost:8000
ENV REACT_APP_WS_URL=$REACT_APP_WS_URL
ARG REACT_APP_API_URL=http://localhost:8031
ENV REACT_APP_API_URL=$REACT_APP_API_URL
RUN npm run build

FROM nginx:stable-alpine
COPY --from=build /app/build /usr/share/nginx/html
EXPOSE 80
