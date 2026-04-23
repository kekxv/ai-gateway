package middleware

import (
	"compress/gzip"
	"io"
	"log"
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/klauspost/compress/zstd"
)

// DecompressMiddleware handles decompression of request bodies based on Content-Encoding header
func DecompressMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		encoding := c.GetHeader("Content-Encoding")
		if encoding == "" {
			c.Next()
			return
		}

		log.Printf("[DecompressMiddleware] Detected Content-Encoding: %s", encoding)

		var reader io.ReadCloser
		var err error

		switch encoding {
		case "gzip":
			reader, err = gzip.NewReader(c.Request.Body)
			if err != nil {
				log.Printf("[DecompressMiddleware] Failed to initialize gzip decompressor: %v", err)
				c.AbortWithStatusJSON(http.StatusBadRequest, gin.H{"error": "Failed to initialize gzip decompressor: " + err.Error()})
				return
			}
		case "zstd":
			var dec *zstd.Decoder
			dec, err = zstd.NewReader(c.Request.Body)
			if err != nil {
				log.Printf("[DecompressMiddleware] Failed to initialize zstd decompressor: %v", err)
				c.AbortWithStatusJSON(http.StatusBadRequest, gin.H{"error": "Failed to initialize zstd decompressor: " + err.Error()})
				return
			}
			reader = dec.IOReadCloser()
		default:
			log.Printf("[DecompressMiddleware] Unsupported encoding: %s", encoding)
			c.Next()
			return
		}

		c.Request.Body = reader
		
		// Optional: Log a snippet of the decompressed body for debugging
		// body, err := io.ReadAll(c.Request.Body)
		// ... (keep commented or remove)
		
		c.Next()
	}
}
