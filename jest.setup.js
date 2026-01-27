// Optional: configure or set up a testing framework before each test.
// If you delete this file, remove `setupFilesAfterEnv` from `jest.config.js`

// Suppress console output in tests to keep output clean
const originalError = console.error;
const originalLog = console.log;

beforeAll(() => {
  console.error = jest.fn();
  console.log = jest.fn();
  
  // Also suppress process-level error handling for unhandled rejections
  process.removeAllListeners('unhandledRejection');
});

afterAll(() => {
  console.error = originalError;
  console.log = originalLog;
});

// Suppress global error handling
global.unhandledRejections = new Map();
process.on('unhandledRejection', () => {
  // Silently ignore
});



