-- RedefineTables
PRAGMA defer_foreign_keys=ON;
PRAGMA foreign_keys=OFF;
CREATE TABLE "new_ModelRoute" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "modelId" INTEGER NOT NULL,
    "channelId" INTEGER NOT NULL,
    "weight" INTEGER NOT NULL DEFAULT 1,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "ModelRoute_modelId_fkey" FOREIGN KEY ("modelId") REFERENCES "Model" ("id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "ModelRoute_channelId_fkey" FOREIGN KEY ("channelId") REFERENCES "Channel" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);
INSERT INTO "new_ModelRoute" ("channelId", "createdAt", "id", "modelId") SELECT "channelId", "createdAt", "id", "modelId" FROM "ModelRoute";
DROP TABLE "ModelRoute";
ALTER TABLE "new_ModelRoute" RENAME TO "ModelRoute";
PRAGMA foreign_keys=ON;
PRAGMA defer_foreign_keys=OFF;
