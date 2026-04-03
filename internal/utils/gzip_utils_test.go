package utils

import (
	"bytes"
	"testing"
)

func TestGzipCompressDecompress(t *testing.T) {
	original := []byte("Hello, World! This is a test string for gzip compression.")

	compressed, err := GzipCompress(original)
	if err != nil {
		t.Fatalf("GzipCompress failed: %v", err)
	}

	// Compressed should be smaller than original for this test string
	if len(compressed) >= len(original) {
		t.Logf("Warning: Compressed size (%d) >= original size (%d)", len(compressed), len(original))
	}

	decompressed, err := GzipDecompress(compressed)
	if err != nil {
		t.Fatalf("GzipDecompress failed: %v", err)
	}

	if !bytes.Equal(original, decompressed) {
		t.Errorf("Decompressed data does not match original")
	}
}

func TestGzipCompressEmpty(t *testing.T) {
	original := []byte{}

	compressed, err := GzipCompress(original)
	if err != nil {
		t.Fatalf("GzipCompress failed: %v", err)
	}

	decompressed, err := GzipDecompress(compressed)
	if err != nil {
		t.Fatalf("GzipDecompress failed: %v", err)
	}

	if !bytes.Equal(original, decompressed) {
		t.Errorf("Decompressed data does not match original")
	}
}