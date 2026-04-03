package utils

import (
	"bytes"
	"compress/gzip"
	"io"
)

// GzipCompress compresses data using gzip
func GzipCompress(data []byte) ([]byte, error) {
	var buf bytes.Buffer
	writer := gzip.NewWriter(&buf)

	if _, err := writer.Write(data); err != nil {
		writer.Close()
		return nil, err
	}

	if err := writer.Close(); err != nil {
		return nil, err
	}

	return buf.Bytes(), nil
}

// GzipDecompress decompresses gzip data
func GzipDecompress(data []byte) ([]byte, error) {
	reader, err := gzip.NewReader(bytes.NewReader(data))
	if err != nil {
		return nil, err
	}
	defer reader.Close()

	return io.ReadAll(reader)
}