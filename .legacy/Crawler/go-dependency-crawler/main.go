package main

import (
	"go-dependency-crawler/internal/config"
	"go-dependency-crawler/internal/crawler"
	"go-dependency-crawler/internal/db"
	"runtime"
)

func main() {
	runtime.GOMAXPROCS(runtime.NumCPU())

	// Load MongoDB connection and HTTP client configurations
	client := db.ConnectMongoDB(config.GetMongoURI())
	defer db.DisconnectMongoDB(client)

	httpClient := config.GetHTTPClient()

	// Start crawling process
	crawler.StartCrawling(client, httpClient)
}