package main

import (
	"io/fs"
	"path"
	"strings"

	"github.com/gin-gonic/gin"
	embedfs "github.com/kekxv/ai-gateway"
)

func setupStaticRoutes(r *gin.Engine) {
	sub, err := fs.Sub(embedfs.DistFS, "web/dist")
	if err != nil {
		return
	}

	// 首页
	r.GET("/", func(c *gin.Context) {
		file, err := sub.Open("index.html")
		if err != nil {
			c.Status(404)
			return
		}
		defer file.Close()

		stat, err := file.Stat()
		if err != nil {
			c.Status(404)
			return
		}

		c.DataFromReader(200, stat.Size(), "text/html; charset=utf-8", file, nil)
	})

	// assets 静态资源
	r.GET("/assets/*filepath", func(c *gin.Context) {
		filepath := c.Param("filepath")
		filepath = strings.TrimPrefix(filepath, "/")

		file, err := sub.Open("assets/" + filepath)
		if err != nil {
			c.Status(404)
			return
		}
		defer file.Close()

		stat, err := file.Stat()
		if err != nil || stat.IsDir() {
			c.Status(404)
			return
		}

		c.DataFromReader(200, stat.Size(), getContentType(filepath), file, nil)
	})

	// locales 静态资源
	r.GET("/locales/*filepath", func(c *gin.Context) {
		filepath := c.Param("filepath")
		filepath = strings.TrimPrefix(filepath, "/")

		file, err := sub.Open("locales/" + filepath)
		if err != nil {
			c.Status(404)
			return
		}
		defer file.Close()

		stat, err := file.Stat()
		if err != nil || stat.IsDir() {
			c.Status(404)
			return
		}

		c.DataFromReader(200, stat.Size(), getContentType(filepath), file, nil)
	})

	// 其他静态文件（如 vite.svg）
	r.GET("/:filename", func(c *gin.Context) {
		filename := c.Param("filename")
		if !isStaticFile(filename) {
			file, err := sub.Open("index.html")
			if err != nil {
				c.Status(404)
				return
			}
			defer file.Close()
			stat, _ := file.Stat()
			c.DataFromReader(200, stat.Size(), "text/html; charset=utf-8", file, nil)
			return
		}

		file, err := sub.Open(filename)
		if err != nil {
			c.Status(404)
			return
		}
		defer file.Close()

		stat, err := file.Stat()
		if err != nil {
			c.Status(404)
			return
		}

		c.DataFromReader(200, stat.Size(), getContentType(filename), file, nil)
	})

	// SPA fallback
	r.NoRoute(func(c *gin.Context) {
		reqPath := c.Request.URL.Path

		if strings.HasPrefix(reqPath, "/api") {
			c.JSON(404, gin.H{"error": "not found"})
			return
		}

		file, err := sub.Open("index.html")
		if err != nil {
			c.JSON(404, gin.H{"error": "not found"})
			return
		}
		defer file.Close()

		stat, err := file.Stat()
		if err != nil {
			c.JSON(404, gin.H{"error": "not found"})
			return
		}

		c.DataFromReader(200, stat.Size(), "text/html; charset=utf-8", file, nil)
	})
}

func isStaticFile(filename string) bool {
	ext := path.Ext(filename)
	staticExts := []string{".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".json", ".xml"}
	for _, e := range staticExts {
		if ext == e {
			return true
		}
	}
	return false
}

func getContentType(filePath string) string {
	ext := path.Ext(filePath)
	switch ext {
	case ".html":
		return "text/html; charset=utf-8"
	case ".css":
		return "text/css; charset=utf-8"
	case ".js":
		return "application/javascript; charset=utf-8"
	case ".json":
		return "application/json; charset=utf-8"
	case ".png":
		return "image/png"
	case ".jpg", ".jpeg":
		return "image/jpeg"
	case ".gif":
		return "image/gif"
	case ".svg":
		return "image/svg+xml"
	case ".ico":
		return "image/x-icon"
	case ".woff", ".woff2":
		return "font/woff2"
	case ".ttf":
		return "font/ttf"
	default:
		return "application/octet-stream"
	}
}