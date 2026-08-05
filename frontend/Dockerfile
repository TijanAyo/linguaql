FROM node:22-alpine

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

ARG NEXT_PUBLIC_API_BASE=https://linguaql-server.brimble.app
ARG NEXT_PUBLIC_DEV_MODE=false
ARG NEXT_PUBLIC_SAMPLE_DB_URL=postgresql://demo_ro:XiWTh2Ij1usNwBczDGr22mjDycTulwWT@ep-dark-lake-avpuxya3-pooler.c-11.us-east-1.aws.neon.tech/neondb?sslmode=require
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
ENV NEXT_PUBLIC_DEV_MODE=$NEXT_PUBLIC_DEV_MODE
ENV NEXT_PUBLIC_SAMPLE_DB_URL=$NEXT_PUBLIC_SAMPLE_DB_URL

RUN npm run build

EXPOSE 3000

CMD npm start
