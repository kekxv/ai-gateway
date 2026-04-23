package utils

import (
	"bytes"
	"testing"
)

func TestZstdCompressDecompress(t *testing.T) {
	original := []byte("Hello, World! This is a test string for zstd compression. It should be long enough to actually benefit from compression if we want to test that, but even short strings should work correctly.")

	compressed, err := ZstdCompress(original)
	if err != nil {
		t.Fatalf("ZstdCompress failed: %v", err)
	}

	decompressed, err := ZstdDecompress(compressed)
	if err != nil {
		t.Fatalf("ZstdDecompress failed: %v", err)
	}

	if !bytes.Equal(original, decompressed) {
		t.Errorf("Decompressed data does not match original")
	}
}

func TestZstdCompressEmpty(t *testing.T) {
	original := []byte{}

	compressed, err := ZstdCompress(original)
	if err != nil {
		t.Fatalf("ZstdCompress failed: %v", err)
	}

	decompressed, err := ZstdDecompress(compressed)
	if err != nil {
		t.Fatalf("ZstdDecompress failed: %v", err)
	}

	if !bytes.Equal(original, decompressed) {
		t.Errorf("Decompressed data does not match original")
	}
}
