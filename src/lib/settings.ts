import { getInitializedDb } from '@/lib/db';
import { randomBytes } from 'crypto';

export async function getJwtSecret(): Promise<string> {
  // Priority 1: Environment variable
  if (process.env.JWT_SECRET) {
    return process.env.JWT_SECRET;
  }

  try {
    const db = await getInitializedDb();
    const setting = await db.get('SELECT value FROM Settings WHERE key = ?', 'JWT_SECRET');
    
    if (setting && setting.value) {
      return setting.value;
    } else {
      // Generate a new random JWT_SECRET and store it in the database
      const newSecret = randomBytes(64).toString('hex');
      await db.run('INSERT OR REPLACE INTO Settings (key, value) VALUES (?, ?)', 'JWT_SECRET', newSecret);
      console.log('Generated and stored new JWT_SECRET in database');
      return newSecret;
    }
  } catch (error) {
    console.error('Error fetching/setting JWT_SECRET from database:', error);
    // Fallback to default (for backward compatibility)
    return 'your_jwt_secret';
  }
}