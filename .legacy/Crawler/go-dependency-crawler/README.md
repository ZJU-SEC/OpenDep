# Go Dependency Crawler

This project is a Go-based tool that crawls Go module dependencies from the Go proxy and stores the metadata in a MongoDB database. It concurrently fetches the dependency information for Go modules and parses their `.mod` files.

## Features

- Crawls Go module dependencies from the [Go Proxy](https://proxy.golang.org/).
- Parses `.mod` files for module information such as dependencies and versions.
- Stores module metadata in MongoDB for later retrieval and analysis.
- Utilizes concurrent goroutines to speed up the crawling process.

## Prerequisites

### 1. Go Installation

Ensure you have [Go](https://golang.org/dl/) installed (version 1.16 or later). You can verify your installation with the following command:

```bash
go version
```

### 2. MongoDB

You need a running instance of MongoDB to store the module metadata. If you don't have MongoDB installed, follow the [installation guide](https://www.mongodb.com/docs/manual/installation/).

You can also use [MongoDB Atlas](https://www.mongodb.com/cloud/atlas) to run a MongoDB instance in the cloud.

## Setup MongoDB

1. Start your MongoDB instance:

   - If you have MongoDB installed locally, start it with the default configuration:
     ```bash
     mongod
     ```
   - If you're using a cloud-hosted MongoDB instance (such as MongoDB Atlas), make sure it's up and running.

2. Create a new database called `GoDependency` and a collection named `metadata`. You can create the database and collection using the following commands in the MongoDB shell:

   ```bash
   use GoDependency
   db.createCollection("metadata")
   ```

3. Update the MongoDB connection URI in the code if necessary. The default URI points to a local instance at `mongodb://localhost:27017`. If you're using a remote MongoDB instance, modify the following line in the `main` function:

   ```go
   client, err := mongo.Connect(context.TODO(), options.Client().ApplyURI("mongodb://localhost:27017").SetConnectTimeout(10*time.Second))
   ```

   Replace `"mongodb://localhost:27017"` with your remote MongoDB URI.

## Project Setup

1. Install dependencies:

   ```bash
   go mod tidy
   ```

2. Configure the HTTP proxy in the code if necessary. The default proxy URL is `http://127.0.0.1:7890`. If you are not using a proxy, you can remove or modify the proxy settings in the `main` function.

3. Set up MongoDB, as described in the "Setup MongoDB" section.

## Running the Project

1. Run the Go program:

   ```bash
   go run main.go
   ```

   The crawler will fetch Go module data starting from the specified `lastModCacheTime` and store the results in MongoDB.

2. You can monitor the results in your MongoDB collection by querying the `metadata` collection:

   ```bash
   use GoDependency
   db.metadata.find().pretty()
   ```

## Configuration

- **MongoDB URI**: Change the MongoDB URI to your desired MongoDB instance.
- **Proxy Settings**: Adjust the proxy settings in the `http.Transport` section if you are using a proxy for outbound HTTP requests.
- **Concurrency**: The number of concurrent goroutines is controlled by the `maxThread` variable. You can modify it to adjust the number of threads based on your system's capacity.

## Error Handling

Errors encountered during module fetching or parsing will be logged into the `err.log` file in the project directory.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

Feel free to adjust the content based on the specifics of your project and deployment environment.