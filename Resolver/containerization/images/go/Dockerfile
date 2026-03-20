FROM cnspary/go-resolver-base:latest

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

RUN set -eu; \
    if [ -f /app/go.mod ] && [ -f /app/cmd/go_resolver/main.go ]; then source_dir=/app; \
    elif [ -f /app/Resolver/containerization/images/go/go.mod ] && [ -f /app/Resolver/containerization/images/go/cmd/go_resolver/main.go ]; then source_dir=/app/Resolver/containerization/images/go; \
    else echo "go source directory not found" >&2; exit 1; fi; \
    cd "$source_dir"; \
    go mod tidy; \
    CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -o /usr/local/bin/go-resolver ./cmd/go_resolver

ENTRYPOINT ["/usr/local/bin/go-resolver"]
