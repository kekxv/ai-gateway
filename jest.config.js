const nextJest = require('next/jest')

const createJestConfig = nextJest({
  // Provide the path to your Next.js app to load next.config.js and .env files in your test environment
  dir: './',
})

// Add any custom config to be passed to Jest
const customJestConfig = {
  setupFilesAfterEnv: ['<rootDir>/jest.setup.js'],
  testEnvironment: 'node',
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
  },
  testMatch: [
    '**/__tests__/**/*.test.ts',
    '**/?(*.)+(spec|test).ts'
  ],
  collectCoverageFrom: [
    'src/**/*.ts',
    '!src/**/*.d.ts',
  ],
  maxWorkers: 1,
  bail: false,
  verbose: false,
  errorOnDeprecated: false,
  coveragePathIgnorePatterns: ['/node_modules/'],
  forceExit: true,
  detectOpenHandles: false,
}

// createJestConfig is exported this way to ensure that next/jest can load the next.config.js which is async
module.exports = createJestConfig(customJestConfig)
