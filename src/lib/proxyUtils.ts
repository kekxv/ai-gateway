import { URL } from 'url';
import * as HttpsProxyAgentModule from 'https-proxy-agent';
import * as HttpProxyAgentModule from 'http-proxy-agent';

const HttpsProxyAgent = (HttpsProxyAgentModule as any).HttpsProxyAgent || (HttpsProxyAgentModule as any).default;
const HttpProxyAgent = (HttpProxyAgentModule as any).HttpProxyAgent || (HttpProxyAgentModule as any).default;

/**
 * Check if an IP address is within a CIDR range
 * @param ip - The IP address to check
 * @param cidr - CIDR notation (e.g., "10.0.0.0/24")
 * @returns true if IP is within the CIDR range
 */
function isIPInCIDR(ip: string, cidr: string): boolean {
  try {
    const [network, bits] = cidr.split('/');
    if (!network || !bits) return false;

    const maskBits = parseInt(bits, 10);
    if (isNaN(maskBits) || maskBits < 0 || maskBits > 32) return false;

    // Convert IP strings to 32-bit integers
    const ipParts = ip.split('.').map(x => parseInt(x, 10));
    const networkParts = network.split('.').map(x => parseInt(x, 10));

    if (ipParts.length !== 4 || networkParts.length !== 4) return false;
    if (ipParts.some(p => isNaN(p) || p < 0 || p > 255)) return false;
    if (networkParts.some(p => isNaN(p) || p < 0 || p > 255)) return false;

    const ipNum = (ipParts[0] << 24) | (ipParts[1] << 16) | (ipParts[2] << 8) | ipParts[3];
    const networkNum = (networkParts[0] << 24) | (networkParts[1] << 16) | (networkParts[2] << 8) | networkParts[3];

    const mask = (0xffffffff << (32 - maskBits)) >>> 0;
    return (ipNum & mask) === (networkNum & mask);
  } catch {
    return false;
  }
}

/**
 * Check if a URL should bypass proxy based on NO_PROXY environment variable
 * @param url - The URL to check
 * @returns true if the URL should bypass proxy, false otherwise
 */
export function shouldBypassProxy(url: string): boolean {
  const noProxy = process.env.NO_PROXY || process.env.no_proxy || '';
  if (!noProxy) {
    return false;
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

      // Handle CIDR notation (e.g., "10.0.0.0/24")
      if (entry.includes('/')) {
        if (isIPInCIDR(hostname, entry)) {
          return true;
        }
        continue;
      }

      // Handle *.example.com pattern
      if (entry.startsWith('*.')) {
        const domain = entry.substring(2);
        // Only match subdomains, not the domain itself
        if (hostname.endsWith('.' + domain)) {
          return true;
        }
        continue;
      }

      // Handle exact domain match or .domain.com pattern
      if (entry.startsWith('.')) {
        if (hostname.endsWith(entry) || hostname === entry.substring(1)) {
          return true;
        }
        continue;
      }

      // Handle exact hostname match or IP address match
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
    console.log(`[PROXY] Bypassing proxy for: ${url}`);
    return {};
  }

  try {
    const urlObj = new URL(url);
    const protocol = urlObj.protocol;

    if (protocol === 'https:') {
      const httpsProxy = process.env.HTTPS_PROXY || process.env.https_proxy;
      if (httpsProxy) {
        console.log(`[PROXY] Using HTTPS proxy: ${httpsProxy} for: ${url}`);
        return { agent: new HttpsProxyAgent(httpsProxy) };
      }
    } else if (protocol === 'http:') {
      const httpProxy = process.env.HTTP_PROXY || process.env.http_proxy;
      if (httpProxy) {
        console.log(`[PROXY] Using HTTP proxy: ${httpProxy} for: ${url}`);
        return { agent: new HttpProxyAgent(httpProxy) };
      }
    }

    console.log(`[PROXY] No proxy configured for protocol: ${protocol}`);
  } catch (_error) {
    // If URL parsing fails, return empty object
    console.log(`[PROXY] Failed to parse URL: ${url}, error: ${_error}`);
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
