package utils

import (
	"testing"
)

func TestShouldBypassProxy(t *testing.T) {
	tests := []struct {
		name      string
		targetURL string
		noProxy   []string
		expected  bool
	}{
		{
			name:      "empty no_proxy",
			targetURL: "https://api.openai.com",
			noProxy:   []string{},
			expected:  false,
		},
		{
			name:      "wildcard match",
			targetURL: "https://api.openai.com",
			noProxy:   []string{"*"},
			expected:  true,
		},
		{
			name:      "exact match",
			targetURL: "https://api.openai.com",
			noProxy:   []string{"api.openai.com"},
			expected:  true,
		},
		{
			name:      "no match",
			targetURL: "https://api.openai.com",
			noProxy:   []string{"api.anthropic.com"},
			expected:  false,
		},
		{
			name:      "wildcard domain",
			targetURL: "https://api.openai.com",
			noProxy:   []string{"*.openai.com"},
			expected:  true,
		},
		{
			name:      "wildcard domain no match",
			targetURL: "https://api.openai.com",
			noProxy:   []string{"*.anthropic.com"},
			expected:  false,
		},
		{
			name:      "domain suffix",
			targetURL: "https://api.openai.com",
			noProxy:   []string{".openai.com"},
			expected:  true,
		},
		{
			name:      "CIDR match",
			targetURL: "https://10.0.0.1",
			noProxy:   []string{"10.0.0.0/8"},
			expected:  true,
		},
		{
			name:      "CIDR no match",
			targetURL: "https://192.168.1.1",
			noProxy:   []string{"10.0.0.0/8"},
			expected:  false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := ShouldBypassProxy(tt.targetURL, tt.noProxy)
			if result != tt.expected {
				t.Errorf("ShouldBypassProxy(%s, %v) = %v, expected %v", tt.targetURL, tt.noProxy, result, tt.expected)
			}
		})
	}
}

func TestParseNoProxy(t *testing.T) {
	tests := []struct {
		name     string
		noProxy  string
		expected int
	}{
		{
			name:     "empty string",
			noProxy:  "",
			expected: 0,
		},
		{
			name:     "single entry",
			noProxy:  "localhost",
			expected: 1,
		},
		{
			name:     "multiple entries",
			noProxy:  "localhost,127.0.0.1,10.0.0.0/8",
			expected: 3,
		},
		{
			name:     "with spaces",
			noProxy:  "localhost, 127.0.0.1, 10.0.0.0/8",
			expected: 3,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := ParseNoProxy(tt.noProxy)
			if len(result) != tt.expected {
				t.Errorf("ParseNoProxy(%s) returned %d entries, expected %d", tt.noProxy, len(result), tt.expected)
			}
		})
	}
}