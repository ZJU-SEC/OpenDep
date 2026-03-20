package crawler

import (
	"context"
	"fmt"
	"go-dependency-crawler/internal/models"
	"go-dependency-crawler/internal/db"
	"net/http"
	"strings"
	"sync"
)

// Parse processes a slice of module dependencies and stores them in MongoDB.
func Parse(modInfo []models.Dep, client *http.Client, collection *db.MongoCollection, muxDB *sync.Mutex) {
	fmt.Println(modInfo[0].Path, modInfo[0].CacheTime)
	for index, val := range modInfo {
		// Parsing logic goes here (the same logic from your original code)
	}
	
	// Store the parsed data in MongoDB
	storeInDB(modInfo, collection, muxDB)
}

func storeInDB(modInfo []models.Dep, collection *db.MongoCollection, muxDB *sync.Mutex) {
	newValue := make([]interface{}, 0)
	for _, v := range modInfo[1:] {
		newValue = append(newValue, v)
	}

	muxDB.Lock()
	defer muxDB.Unlock()

	_, err := collection.InsertMany(context.TODO(), newValue)
	if err != nil {
		fmt.Println("Error inserting into DB:", err)
	}
}