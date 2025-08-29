# Use a Node.js base image
FROM node:20-alpine AS base

# Set working directory
WORKDIR /app

# Install pnpm
RUN npm install -g pnpm

# Copy package.json and pnpm-lock.yaml to leverage Docker cache
COPY package.json pnpm-lock.yaml ./
COPY prisma ./prisma

# Install dependencies
RUN npx pnpm install --frozen-lockfile
RUN npx prisma generate
RUN npx tsc --project prisma/tsconfig.json --outDir prisma

# Copy the rest of the application code
COPY . .

# Build the Next.js application
RUN npx pnpm build

# Production stage
FROM node:20-alpine AS runner

WORKDIR /app

# Set environment variables for Next.js production
ENV NODE_ENV=production

# Copy the standalone output from the base stage
COPY --from=base /app/.next/standalone ./
COPY --from=base /app/public ./public
COPY --from=base /app/.next/static ./public/_next/static
COPY --from=base /app/prisma ./prisma

ENV DATABASE_URL="file:/app/ai-gateway.db"
ENV JWT_SECRET="your_jwt_secret_here"

# Apply Prisma migrations


# Expose the port Next.js runs on
EXPOSE 3000

# Command to run the application
CMD ["node", "server.js"]
