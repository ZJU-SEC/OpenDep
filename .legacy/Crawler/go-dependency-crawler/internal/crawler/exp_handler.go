package crawler

import (
	"log"
	"os"
)

// ExpHandler logs the error details to a log file.
func ExpHandler(cacheTime string, e error) {
	logFile, err := os.OpenFile("./err.log", os.O_WRONLY|os.O_CREATE|os.O_APPEND, 0666)
	if err != nil {
		panic(err)
	}
	log.SetOutput(logFile)
	log.Println(cacheTime, e)
}