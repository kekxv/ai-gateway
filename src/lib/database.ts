import sqlite3 from 'sqlite3';
import { open } from 'sqlite';
import path from 'path';
import fs from 'fs';

const DB_PATH = process.env.DATABASE_URL ? process.env.DATABASE_URL.replace('file:', '') : path.resolve(process.cwd(), 'ai-gateway.db');

const schema = `
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS User (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  password TEXT NOT NULL,
  role TEXT DEFAULT 'USER' NOT NULL,
  disabled BOOLEAN DEFAULT FALSE NOT NULL,
  validUntil DATETIME,
  createdAt DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
  totpSecret TEXT,
  totpEnabled BOOLEAN DEFAULT FALSE NOT NULL
);

CREATE TABLE IF NOT EXISTS Provider (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL,
  baseURL TEXT NOT NULL,
  apiKey TEXT,
  type TEXT,
  createdAt DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
  userId INTEGER,
  FOREIGN KEY (userId) REFERENCES User(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS Channel (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL,
  enabled BOOLEAN DEFAULT TRUE NOT NULL,
  createdAt DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
  updatedAt DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
  providerId INTEGER NOT NULL,
  userId INTEGER,
  FOREIGN KEY (providerId) REFERENCES Provider(id) ON DELETE CASCADE,
  FOREIGN KEY (userId) REFERENCES User(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS Model (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL,
  description TEXT,
  createdAt DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
  updatedAt DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
  userId INTEGER,
  FOREIGN KEY (userId) REFERENCES User(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS ProviderModel (
  providerId INTEGER NOT NULL,
  modelId INTEGER NOT NULL,
  PRIMARY KEY (providerId, modelId),
  FOREIGN KEY (providerId) REFERENCES Provider(id) ON DELETE CASCADE,
  FOREIGN KEY (modelId) REFERENCES Model(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ModelRoute (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  modelId INTEGER NOT NULL,
  channelId INTEGER NOT NULL,
  weight INTEGER DEFAULT 1 NOT NULL,
  createdAt DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
  FOREIGN KEY (modelId) REFERENCES Model(id) ON DELETE CASCADE,
  FOREIGN KEY (channelId) REFERENCES Channel(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS GatewayApiKey (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  key TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  enabled BOOLEAN DEFAULT TRUE NOT NULL,
  createdAt DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
  lastUsed DATETIME,
  userId INTEGER,
  FOREIGN KEY (userId) REFERENCES User(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS Log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  latency INTEGER NOT NULL,
  promptTokens INTEGER DEFAULT 0 NOT NULL,
  completionTokens INTEGER DEFAULT 0 NOT NULL,
  totalTokens INTEGER DEFAULT 0 NOT NULL,
  createdAt DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
  apiKeyId INTEGER NOT NULL,
  modelRouteId INTEGER NOT NULL,
  FOREIGN KEY (apiKeyId) REFERENCES GatewayApiKey(id) ON DELETE CASCADE,
  FOREIGN KEY (modelRouteId) REFERENCES ModelRoute(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS LogDetail (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  logId INTEGER UNIQUE NOT NULL,
  requestBody TEXT,
  responseBody TEXT,
  createdAt DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
  FOREIGN KEY (logId) REFERENCES Log(id) ON DELETE CASCADE
);
`;

let dbInstance: any;

export async function initializeDatabase() {
  const dbExists = fs.existsSync(DB_PATH);

  dbInstance = await open({
    filename: DB_PATH,
    driver: sqlite3.Database,
  });

  if (!dbExists) {
    console.log('Database file not found, initializing schema...');
    await dbInstance.exec(schema);
    console.log('Database schema initialized.');
  } else {
    console.log('Database file found, skipping schema initialization.');
  }

  return dbInstance;
}

export function getDb() {
  if (!dbInstance) {
    throw new Error('Database not initialized. Call initializeDatabase() first.');
  }
  return dbInstance;
}
