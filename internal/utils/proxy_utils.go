package utils

import (
	"net/netip"
	"net/url"
	"strings"
)

// ShouldBypassProxy checks if the target URL should bypass proxy based on no_proxy settings
func ShouldBypassProxy(targetURL string, noProxyEntries []string) bool {
	if len(noProxyEntries) == 0 {
		return false
	}

	u, err := url.Parse(targetURL)
	if err != nil {
		return false
	}

	hostname := u.Hostname()

	for _, entry := range noProxyEntries {
		entry = strings.TrimSpace(entry)
		if entry == "" {
			continue
		}

		// Wildcard matches everything
		if entry == "*" {
			return true
		}

		// CIDR matching (e.g., 10.0.0.0/8)
		if strings.Contains(entry, "/") {
			if matchCIDR(hostname, entry) {
				return true
			}
			continue
		}

		// Wildcard domain (*.example.com)
		if strings.HasPrefix(entry, "*.") {
			domain := entry[2:]
			if strings.HasSuffix(hostname, "."+domain) || hostname == domain {
				return true
			}
			continue
		}

		// Domain suffix (.example.com matches subdomains)
		if strings.HasPrefix(entry, ".") {
			if strings.HasSuffix(hostname, entry) || hostname == entry[1:] {
				return true
			}
			continue
		}

		// Exact match
		if hostname == entry {
			return true
		}
	}

	return false
}

func matchCIDR(ip string, cidr string) bool {
	addr, err := netip.ParseAddr(ip)
	if err != nil {
		return false
	}

	prefix, err := netip.ParsePrefix(cidr)
	if err != nil {
		return false
	}

	return prefix.Contains(addr)
}

// ParseNoProxy parses NO_PROXY environment variable into a list of entries
func ParseNoProxy(noProxy string) []string {
	if noProxy == "" {
		return nil
	}

	entries := strings.Split(noProxy, ",")
	result := make([]string, 0, len(entries))
	for _, entry := range entries {
		entry = strings.TrimSpace(entry)
		if entry != "" {
			result = append(result, entry)
		}
	}
	return result
}