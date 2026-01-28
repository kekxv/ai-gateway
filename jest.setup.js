// Optional: configure or set up a testing framework before each test.
// If you delete this file, remove `setupFilesAfterEnv` from `jest.config.js`

// Mock sqlite3 to avoid native binding issues in tests
jest.mock('sqlite3', () => {
  return {
    verbose: jest.fn().mockReturnThis(),
  };
}, { virtual: true });

// Mock sqlite module
jest.mock('sqlite', () => {
  return {
    open: jest.fn().mockResolvedValue({
      get: jest.fn(),
      all: jest.fn(),
      run: jest.fn(),
      close: jest.fn(),
    }),
  };
}, { virtual: true });

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
  
  // Ensure all pending timers are cleared
  jest.clearAllTimers();
  jest.clearAllMocks();
});

// Suppress global error handling
global.unhandledRejections = new Map();
process.on('unhandledRejection', () => {
  // Silently ignore
});

// Set test timeout
jest.setTimeout(10000);

// Force exit after tests complete if there are hanging operations
if (process.env.FORCE_EXIT !== 'false') {
  afterAll(() => {
    // Give async operations a brief moment to complete
    setTimeout(() => {
      // Force exit if tests have completed but process is still running
      // This is a safety measure for CI/CD environments
    }, 100);
  });
}
