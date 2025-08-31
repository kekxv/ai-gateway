import { initializeDatabase } from './database';

declare global {
  var __dbPromise: Promise<any>; // Use a promise to ensure it's only initialized once
}

const globalForDb = global as typeof globalThis & {
  __dbPromise?: Promise<any>;
};

export async function getInitializedDb(): Promise<any> {
  if (process.env.NODE_ENV === 'production') {
    if (!globalForDb.__dbPromise) {
      globalForDb.__dbPromise = initializeDatabase();
    }
    return await globalForDb.__dbPromise;
  } else {
    // In development, use global to prevent multiple initializations across hot reloads
    if (!globalForDb.__dbPromise) {
      globalForDb.__dbPromise = initializeDatabase();
    }
    return await globalForDb.__dbPromise;
  }
}
