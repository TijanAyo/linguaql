FROM node:22-alpine

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

EXPOSE 3000
# Dev server keeps the skeleton simple (no build step / standalone output).
CMD ["npm", "run", "dev"]
