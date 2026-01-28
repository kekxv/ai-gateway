import { URL } from 'url';
import * as HttpsProxyAgentModule from 'https-proxy-agent';
import * as HttpProxyAgentModule from 'http-proxy-agent';

const HttpsProxyAgent = (HttpsProxyAgentModule as any).HttpsProxyAgent || (HttpsProxyAgentModule as any).default;
const HttpProxyAgent = (HttpProxyAgentModule as any).HttpProxyAgent || (HttpProxyAgentModule as any).default;

/**
 * Check if a URL should bypass proxy based on NO_PROXY environment variable
 * @param url - The URL to check
 * @returns true if the URL should bypass proxy, false otherwise
 */
export function shouldBypassProxy(url: string): boolean {
  const noProxy = process.env.NO_PROXY || process.env.no_proxy || '';
  if (!noProxy) {
    return true;
  }

  try {
    const urlObj = new URL(url);
    const hostname = urlObj.hostname;

    // Parse NO_PROXY entries (comma-separated)
    const entries = noProxy.split(',').map((entry) => entry.trim());

    for (const entry of entries) {
      if (!entry) continue;

      // Support wildcards and exact matches
      if (entry === '*') {
        return true;
      }

      // Handle *.example.com pattern
      if (entry.startsWith('*.')) {
        const domain = entry.substring(2);
        // Only match subdomains, not the domain itself
        if (hostname.endsWith('.' + domain)) {
          return true;
        }
      }

      // Handle exact domain match or .domain.com pattern
      if (entry.startsWith('.')) {
        if (hostname.endsWith(entry) || hostname === entry.substring(1)) {
          return true;
        }
      }

      // Handle exact hostname match
      if (hostname === entry) {
        return true;
      }
    }

    return false;
  } catch (_error) {
    return false;
  }
}

/**
 * Get appropriate proxy agent for a URL based on environment variables
 * @param url - The URL to create agent for
 * @returns RequestInit with appropriate agent, or empty object if no proxy needed
 */
export function getProxyAgent(url: string): { agent?: any; } {
  if (shouldBypassProxy(url)) {
    return {};
  }

  try {
    const urlObj = new URL(url);
    const protocol = urlObj.protocol;

    if (protocol === 'https:') {
      const httpsProxy = process.env.HTTPS_PROXY || process.env.https_proxy;
      if (httpsProxy) {
        return { agent: new HttpsProxyAgent(httpsProxy) };
      }
    } else if (protocol === 'http:') {
      const httpProxy = process.env.HTTP_PROXY || process.env.http_proxy;
      if (httpProxy) {
        return { agent: new HttpProxyAgent(httpProxy) };
      }
    }
  } catch (_error) {
    // If URL parsing fails, return empty object
  }

  return {};
}

/**
 * Create fetch options with proxy support
 * @param url - The URL to fetch
 * @param options - Base fetch options
 * @returns Merged fetch options with proxy agent if applicable
 */
export function withProxySupport(url: string, options: RequestInit = {}): RequestInit {
  const proxyOptions = getProxyAgent(url);
  return { ...options, ...proxyOptions };
}
