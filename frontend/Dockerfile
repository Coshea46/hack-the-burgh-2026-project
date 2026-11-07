FROM node:18-alpine

WORKDIR /app

COPY sports-streaming-service/package*.json ./

RUN npm install

COPY sports-streaming-service/ ./

EXPOSE 3000
CMD ["npm", "run", "start"]