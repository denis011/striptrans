FROM node:24-slim
WORKDIR /e2e
COPY package.json ./
RUN npm install --no-audit --no-fund && npx playwright install --with-deps chromium
COPY . .
CMD ["npx", "playwright", "test"]
