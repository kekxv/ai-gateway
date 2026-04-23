package middleware

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/kekxv/ai-gateway/internal/utils"
)

func TestDecompressMiddleware(t *testing.T) {
	gin.SetMode(gin.TestMode)

	// Create a dummy handler that reads the body and returns it
	dummyHandler := func(c *gin.Context) {
		body, err := io.ReadAll(c.Request.Body)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		
		var data map[string]interface{}
		if err := json.Unmarshal(body, &data); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid json: " + err.Error()})
			return
		}
		
		c.JSON(http.StatusOK, data)
	}

	router := gin.New()
	router.Use(DecompressMiddleware())
	router.POST("/test", dummyHandler)

	testData := map[string]interface{}{"message": "hello world", "status": "ok"}
	jsonData, _ := json.Marshal(testData)

	t.Run("NoCompression", func(t *testing.T) {
		req := httptest.NewRequest("POST", "/test", bytes.NewReader(jsonData))
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		if w.Code != http.StatusOK {
			t.Errorf("Expected 200, got %d: %s", w.Code, w.Body.String())
		}
		
		var resp map[string]interface{}
		json.Unmarshal(w.Body.Bytes(), &resp)
		if resp["message"] != "hello world" {
			t.Errorf("Expected 'hello world', got %v", resp["message"])
		}
	})

	t.Run("GzipCompression", func(t *testing.T) {
		compressed, _ := utils.GzipCompress(jsonData)
		req := httptest.NewRequest("POST", "/test", bytes.NewReader(compressed))
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("Content-Encoding", "gzip")
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		if w.Code != http.StatusOK {
			t.Errorf("Expected 200, got %d: %s", w.Code, w.Body.String())
		}
		
		var resp map[string]interface{}
		json.Unmarshal(w.Body.Bytes(), &resp)
		if resp["message"] != "hello world" {
			t.Errorf("Expected 'hello world', got %v", resp["message"])
		}
	})

	t.Run("ZstdCompression", func(t *testing.T) {
		compressed, _ := utils.ZstdCompress(jsonData)
		req := httptest.NewRequest("POST", "/test", bytes.NewReader(compressed))
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("Content-Encoding", "zstd")
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		if w.Code != http.StatusOK {
			t.Errorf("Expected 200, got %d: %s", w.Code, w.Body.String())
		}
		
		var resp map[string]interface{}
		json.Unmarshal(w.Body.Bytes(), &resp)
		if resp["message"] != "hello world" {
			t.Errorf("Expected 'hello world', got %v", resp["message"])
		}
	})

	t.Run("InvalidCompression", func(t *testing.T) {
		req := httptest.NewRequest("POST", "/test", bytes.NewReader([]byte("not compressed")))
		req.Header.Set("Content-Encoding", "zstd")
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		if w.Code != http.StatusBadRequest {
			t.Errorf("Expected 400 for invalid compression, got %d: %s", w.Code, w.Body.String())
		}
	})

	t.Run("VerifyHeaderPreserved", func(t *testing.T) {
		compressed, _ := utils.ZstdCompress(jsonData)
		req := httptest.NewRequest("POST", "/test", bytes.NewReader(compressed))
		req.Header.Set("Content-Encoding", "zstd")
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		if w.Code != http.StatusOK {
			t.Errorf("Expected 200, got %d", w.Code)
		}
		// The middleware should NOT remove the header, it only decompresses the body.
		// The service is responsible for not forwarding it.
		if req.Header.Get("Content-Encoding") != "zstd" {
			t.Errorf("Expected Content-Encoding header to be preserved for the handler")
		}
	})
}
