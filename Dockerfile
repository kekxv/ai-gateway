FROM node:20-alpine AS base

# Set working directory
WORKDIR /app

# Copy package.json and package-lock.json to leverage Docker cache
COPY package.json package-lock.json ./

# Install dependencies
RUN npm install

# Copy the rest of the application code
COPY . .

# Build the Next.js application
RUN npm run build

# Production stage
FROM node:20-alpine AS runner

WORKDIR /app

# Set environment variables for Next.js production
ENV NODE_ENV=production

# Copy the standalone output from the base stage
COPY --from=base /app/.next/standalone ./
COPY --from=base /app/public ./public
COPY --from=base /app/.next/static ./public/_next/static

# Set the database URL to point to the dev.db file in the app directory
ENV DATABASE_URL="file:/app/ai-gateway.db"
ENV JWT_SECRET="your_jwt_secret_here"

# Expose the port Next.js runs on
EXPOSE 3000

# Command to run the application
CMD ["node", "server.js"]
