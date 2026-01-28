import { getProxyAgent, withProxySupport, shouldBypassProxy } from '../proxyUtils';

describe('Proxy Utils', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    // Clear all proxy-related environment variables
    process.env = { ...originalEnv };
    delete process.env.HTTP_PROXY;
    delete process.env.HTTPS_PROXY;
    delete process.env.http_proxy;
    delete process.env.https_proxy;
    delete process.env.NO_PROXY;
    delete process.env.no_proxy;
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  describe('shouldBypassProxy', () => {
    it('should return false when NO_PROXY is not set', () => {
      const result = shouldBypassProxy('https://api.example.com');
      expect(result).toBe(false);
    });

    it('should bypass all domains when NO_PROXY=*', () => {
      process.env.NO_PROXY = '*';
      expect(shouldBypassProxy('https://api.example.com')).toBe(true);
      expect(shouldBypassProxy('http://localhost:3000')).toBe(true);
    });

    it('should bypass exact domain match', () => {
      process.env.NO_PROXY = 'api.example.com';
      expect(shouldBypassProxy('https://api.example.com')).toBe(true);
      expect(shouldBypassProxy('https://other.example.com')).toBe(false);
    });

    it('should bypass subdomain with wildcard pattern', () => {
      process.env.NO_PROXY = '*.example.com';
      expect(shouldBypassProxy('https://api.example.com')).toBe(true);
      expect(shouldBypassProxy('https://cdn.example.com')).toBe(true);
      expect(shouldBypassProxy('https://example.com')).toBe(false);
    });

    it('should bypass domain with leading dot', () => {
      process.env.NO_PROXY = '.example.com';
      expect(shouldBypassProxy('https://api.example.com')).toBe(true);
      expect(shouldBypassProxy('https://example.com')).toBe(true);
      expect(shouldBypassProxy('https://other.com')).toBe(false);
    });

    it('should handle comma-separated NO_PROXY entries', () => {
      process.env.NO_PROXY = 'localhost,.local,*.internal.com';
      expect(shouldBypassProxy('http://localhost:3000')).toBe(true);
      expect(shouldBypassProxy('https://api.local')).toBe(true);
      expect(shouldBypassProxy('https://service.internal.com')).toBe(true);
      expect(shouldBypassProxy('https://external.com')).toBe(false);
    });

    it('should handle no_proxy (lowercase)', () => {
      process.env.no_proxy = 'localhost';
      expect(shouldBypassProxy('http://localhost:3000')).toBe(true);
    });

    it('should bypass CIDR IP ranges', () => {
      process.env.NO_PROXY = '10.0.0.0/24,172.16.0.0/12';
      // IPs within CIDR range
      expect(shouldBypassProxy('http://10.0.0.1')).toBe(true);
      expect(shouldBypassProxy('http://10.0.0.250')).toBe(true);
      expect(shouldBypassProxy('http://172.16.0.1')).toBe(true);
      expect(shouldBypassProxy('http://172.31.255.255')).toBe(true);
      // IPs outside CIDR range
      expect(shouldBypassProxy('http://10.0.1.1')).toBe(false);
      expect(shouldBypassProxy('http://172.32.0.1')).toBe(false);
      expect(shouldBypassProxy('http://8.8.8.8')).toBe(false);
    });

    it('should handle mixed NO_PROXY entries with CIDR, wildcards and domains', () => {
      process.env.NO_PROXY = 'localhost,10.0.0.0/24,*.internal,api.example.com';
      // Should bypass localhost
      expect(shouldBypassProxy('http://localhost:3000')).toBe(true);
      // Should bypass CIDR range
      expect(shouldBypassProxy('http://10.0.0.100')).toBe(true);
      // Should bypass wildcard domains
      expect(shouldBypassProxy('https://service.internal')).toBe(true);
      // Should bypass exact match
      expect(shouldBypassProxy('https://api.example.com')).toBe(true);
      // Should NOT bypass external domains
      expect(shouldBypassProxy('https://external.api.com')).toBe(false);
    });

    it('should return false when NO_PROXY is not set (meaning use proxy)', () => {
      // When NO_PROXY is not set, shouldBypassProxy returns false (i.e., use proxy)
      delete process.env.NO_PROXY;
      delete process.env.no_proxy;
      expect(shouldBypassProxy('https://api.openai.com')).toBe(false);
      expect(shouldBypassProxy('https://integrate.api.nvidia.com/v1')).toBe(false);
    });
  });

  describe('getProxyAgent', () => {
    it('should return empty object when no proxy is set', () => {
      const result = getProxyAgent('https://api.example.com');
      expect(result).toEqual({});
    });

    it('should return empty object when URL should bypass proxy', () => {
      process.env.HTTPS_PROXY = 'http://proxy.example.com:8080';
      process.env.NO_PROXY = '*.example.com';
      const result = getProxyAgent('https://api.example.com');
      expect(result).toEqual({});
    });

    it('should return agent for HTTPS_PROXY', () => {
      process.env.HTTPS_PROXY = 'http://proxy.example.com:8080';
      const result = getProxyAgent('https://api.openai.com');
      expect(result).toHaveProperty('agent');
      expect(result.agent).toBeDefined();
    });

    it('should return agent for HTTP_PROXY', () => {
      process.env.HTTP_PROXY = 'http://proxy.example.com:8080';
      const result = getProxyAgent('http://api.example.com');
      expect(result).toHaveProperty('agent');
      expect(result.agent).toBeDefined();
    });

    it('should use lowercase proxy environment variables as fallback', () => {
      process.env.https_proxy = 'http://proxy.example.com:8080';
      const result = getProxyAgent('https://api.example.com');
      expect(result).toHaveProperty('agent');
    });

    it('should handle invalid URLs gracefully', () => {
      process.env.HTTPS_PROXY = 'http://proxy.example.com:8080';
      const result = getProxyAgent('not a valid url');
      expect(result).toEqual({});
    });
  });

  describe('withProxySupport', () => {
    it('should merge proxy options with existing options', () => {
      process.env.HTTPS_PROXY = 'http://proxy.example.com:8080';
      const options = {
        method: 'GET',
        headers: {
          'Authorization': 'Bearer token',
        },
      };
      const result = withProxySupport('https://api.example.com', options);
      expect(result).toHaveProperty('method', 'GET');
      expect(result).toHaveProperty('headers');
      expect(result).toHaveProperty('agent');
    });

    it('should not add agent if NO_PROXY matches', () => {
      process.env.HTTPS_PROXY = 'http://proxy.example.com:8080';
      process.env.NO_PROXY = 'localhost';
      const result = withProxySupport('http://localhost:3000', {});
      expect(result).not.toHaveProperty('agent');
    });
  });
});
