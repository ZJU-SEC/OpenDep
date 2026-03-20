package config

import (
	"crypto/tls"
	"net/http"
	"net/url"
	"time"
)

// GetMongoURI returns the MongoDB connection URI.
func GetMongoURI() string {
	return "mongodb://localhost:27017"
}

// GetHTTPClient initializes and returns an HTTP client with proxy and TLS configuration.
func GetHTTPClient() *http.Client {
	proxyUrl := "http://127.0.0.1:7890"
	proxy, _ := url.Parse(proxyUrl)

	tr := &http.Transport{
		Proxy:           http.ProxyURL(proxy),
		TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
	}

	return &http.Client{
		Transport: tr,
		Timeout:   120 * time.Second,
	}
}