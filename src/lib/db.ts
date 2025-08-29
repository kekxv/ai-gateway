import { initializeDatabase, getDb as getDbInstance } from './database';

declare global {
  var __db: any; // Use a different global variable name to avoid conflicts
}

const globalForDb = global as typeof globalThis & {
  __db?: any;
};

let db: any;

if (process.env.NODE_ENV === 'production') {
  db = initializeDatabase(); // In production, initialize directly
} else {
  if (!globalForDb.__db) {
    globalForDb.__db = initializeDatabase(); // In development, use global to prevent multiple initializations
  }
  db = globalForDb.__db;
}

// Export a function that returns the awaited db instance
export async function getInitializedDb() {
  return await db;
}
