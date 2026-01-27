/**
 * Timeout configuration for external requests
 * All values are in milliseconds
 */
export const TIMEOUT_CONFIG = {
  // Connection timeout - time to establish a connection
  CONNECTION_TIMEOUT: parseInt(process.env.FETCH_CONNECTION_TIMEOUT || '10000', 10),
  
  // Read/Response timeout - time to receive a response once connected
  RESPONSE_TIMEOUT: parseInt(process.env.FETCH_RESPONSE_TIMEOUT || '60000', 10),
  
  // Total timeout - maximum time for entire request
  TOTAL_TIMEOUT: parseInt(process.env.FETCH_TOTAL_TIMEOUT || '120000', 10),
  
  // Model loading timeout - for loading models from providers
  MODEL_LOAD_TIMEOUT: parseInt(process.env.FETCH_MODEL_LOAD_TIMEOUT || '30000', 10),
};

/**
 * Create an AbortSignal with timeout
 * @param timeoutMs - Timeout in milliseconds
 * @returns AbortSignal that aborts after timeout
 */
export function createTimeoutSignal(timeoutMs: number): AbortSignal {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => {
    controller.abort();
  }, timeoutMs);

  // Clean up timeout if signal is aborted for other reasons
  controller.signal.addEventListener('abort', () => {
    clearTimeout(timeoutId);
  }, { once: true });

  return controller.signal;
}

/**
 * Get timeout configuration for different request types
 */
export function getTimeoutForRequestType(type: 'upstream' | 'model-load' | 'model-sync' | 'response'): number {
  switch (type) {
    case 'model-load':
      return TIMEOUT_CONFIG.MODEL_LOAD_TIMEOUT;
    case 'model-sync':
      return TIMEOUT_CONFIG.MODEL_LOAD_TIMEOUT;
    case 'response':
      return TIMEOUT_CONFIG.RESPONSE_TIMEOUT;
    case 'upstream':
    default:
      return TIMEOUT_CONFIG.TOTAL_TIMEOUT;
  }
}

/**
 * Log timeout configuration on startup
 */
export function logTimeoutConfig(): void {
  console.log('[TIMEOUT] Configuration loaded:', {
    connectionTimeout: `${TIMEOUT_CONFIG.CONNECTION_TIMEOUT}ms`,
    responseTimeout: `${TIMEOUT_CONFIG.RESPONSE_TIMEOUT}ms`,
    totalTimeout: `${TIMEOUT_CONFIG.TOTAL_TIMEOUT}ms`,
    modelLoadTimeout: `${TIMEOUT_CONFIG.MODEL_LOAD_TIMEOUT}ms`,
  });
}
