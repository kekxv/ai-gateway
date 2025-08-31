import sqlite3 from 'sqlite3';
import { open } from 'sqlite';
import path from 'path';
import fs from 'fs';

const DB_PATH = process.env.DATABASE_URL ? process.env.DATABASE_URL.replace('file:', '') : path.resolve(process.cwd(), 'ai-gateway.db');

const DATABASE_SCHEMA_VERSION = 4;

const schema = `
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS SchemaVersion (
  version INTEGER PRIMARY KEY,
  appliedAt DATETIME DEFAULT CURRENT_TIMESTAMP
);

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

const migrations = [
  {
    version: 1,
    name: 'add_autoLoadModels_to_provider',
    up: `ALTER TABLE Provider ADD COLUMN autoLoadModels BOOLEAN DEFAULT FALSE NOT NULL;`,
  },
  {
    version: 2,
    name: 'add_alias_to_model',
    up: `ALTER TABLE Model ADD COLUMN alias TEXT;`,
  },
  {
    version: 3,
    name: 'add_channel_provider_many_to_many',
    up: `
      CREATE TABLE IF NOT EXISTS ChannelProvider (
        channelId INTEGER NOT NULL,
        providerId INTEGER NOT NULL,
        PRIMARY KEY (channelId, providerId),
        FOREIGN KEY (channelId) REFERENCES Channel(id) ON DELETE CASCADE,
        FOREIGN KEY (providerId) REFERENCES Provider(id) ON DELETE CASCADE
      );

      -- Optional: Migrate existing data if needed.
      -- INSERT INTO ChannelProvider (channelId, providerId)
      -- SELECT id, providerId FROM Channel WHERE providerId IS NOT NULL;

      CREATE TEMPORARY TABLE Channel_backup(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        enabled BOOLEAN DEFAULT TRUE NOT NULL,
        createdAt DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updatedAt DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
        userId INTEGER
      );

      INSERT INTO Channel_backup SELECT id, name, enabled, createdAt, updatedAt, userId FROM Channel;
      DROP TABLE Channel;

      CREATE TABLE Channel (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        enabled BOOLEAN DEFAULT TRUE NOT NULL,
        createdAt DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updatedAt DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
        userId INTEGER,
        FOREIGN KEY (userId) REFERENCES User(id) ON DELETE SET NULL
      );

      INSERT INTO Channel SELECT id, name, enabled, createdAt, updatedAt, userId FROM Channel_backup;
      DROP TABLE Channel_backup;
    `,
  },
  {
    version: 4,
    name: 'add_api_key_channel_binding',
    up: `
      ALTER TABLE GatewayApiKey ADD COLUMN bindToAllChannels BOOLEAN DEFAULT FALSE NOT NULL;

      CREATE TABLE IF NOT EXISTS GatewayApiKeyChannel (
        apiKeyId INTEGER NOT NULL,
        channelId INTEGER NOT NULL,
        PRIMARY KEY (apiKeyId, channelId),
        FOREIGN KEY (apiKeyId) REFERENCES GatewayApiKey(id) ON DELETE CASCADE,
        FOREIGN KEY (channelId) REFERENCES Channel(id) ON DELETE CASCADE
      );
    `,
  },
  // Add future migrations here
];

async function runMigrations(db: any) {
  console.log('Ensuring SchemaVersion table exists...');
  await db.exec(`
    CREATE TABLE IF NOT EXISTS SchemaVersion (
      version INTEGER PRIMARY KEY,
      appliedAt DATETIME DEFAULT CURRENT_TIMESTAMP
    );
  `);
  console.log('SchemaVersion table check complete.');

  let currentVersion = 0;
  try {
    const versionRow = await db.get('SELECT version FROM SchemaVersion ORDER BY version DESC LIMIT 1');
    if (versionRow) {
      currentVersion = versionRow.version;
      console.log('Found existing database version:', currentVersion);
    } else {
      console.log('No existing schema version found in database. Assuming version 0.');
    }
  } catch (e) {
    console.warn('Could not read schema version, assuming 0. Error:', e);
    currentVersion = 0;
  }

  console.log('Current database version for migration check:', currentVersion);

  let migrationsApplied = 0;
  for (const migration of migrations) {
    if (migration.version > currentVersion) {
      console.log(`Applying migration v${migration.version}: ${migration.name}...`);
      await db.exec(migration.up);
      await db.run('INSERT INTO SchemaVersion (version) VALUES (?)', migration.version);
      console.log(`Migration v${migration.version} (${migration.name}) applied successfully.`);
      migrationsApplied++;
    }
  }
  if (migrationsApplied > 0) {
    console.log(`Successfully applied ${migrationsApplied} new migrations.`);
  } else {
    console.log('No new migrations to apply.');
  }
  console.log('Database migration check complete.');
}

export async function initializeDatabase() {
  const dbExists = fs.existsSync(DB_PATH);

  dbInstance = await open({
    filename: DB_PATH,
    driver: sqlite3.Database,
  });

  if (!dbExists) {
    console.log('Database file not found, initializing base schema...');
    await dbInstance.exec(schema);
    await dbInstance.run('INSERT INTO SchemaVersion (version) VALUES (?)', 0);
    console.log('Database schema initialized to version', DATABASE_SCHEMA_VERSION);
  }

  // Always run migrations after opening the database. The runMigrations function itself
  // will determine if any migrations need to be applied based on the SchemaVersion table.
  await runMigrations(dbInstance);

  return dbInstance;
}
