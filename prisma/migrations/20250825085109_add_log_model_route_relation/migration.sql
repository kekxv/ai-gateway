/*
  Warnings:

  - You are about to drop the column `model` on the `Log` table. All the data in the column will be lost.
  - Added the required column `modelRouteId` to the `Log` table without a default value. This is not possible if the table is not empty.

*/
-- RedefineTables
PRAGMA defer_foreign_keys=ON;
PRAGMA foreign_keys=OFF;
CREATE TABLE "new_Log" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "latency" INTEGER NOT NULL,
    "promptTokens" INTEGER NOT NULL DEFAULT 0,
    "completionTokens" INTEGER NOT NULL DEFAULT 0,
    "totalTokens" INTEGER NOT NULL DEFAULT 0,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "apiKeyId" INTEGER NOT NULL,
    "modelRouteId" INTEGER NOT NULL,
    CONSTRAINT "Log_apiKeyId_fkey" FOREIGN KEY ("apiKeyId") REFERENCES "GatewayApiKey" ("id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "Log_modelRouteId_fkey" FOREIGN KEY ("modelRouteId") REFERENCES "ModelRoute" ("id") ON DELETE RESTRICT ON UPDATE CASCADE
);
INSERT INTO "new_Log" ("apiKeyId", "completionTokens", "createdAt", "id", "latency", "promptTokens", "totalTokens") SELECT "apiKeyId", "completionTokens", "createdAt", "id", "latency", "promptTokens", "totalTokens" FROM "Log";
DROP TABLE "Log";
ALTER TABLE "new_Log" RENAME TO "Log";
PRAGMA foreign_keys=ON;
PRAGMA defer_foreign_keys=OFF;
