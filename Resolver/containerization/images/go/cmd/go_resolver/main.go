package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"net/http"
	"os"
	"time"

	"github.com/package-dependency/go-resolver/internal/output"
	"github.com/package-dependency/go-resolver/internal/resolver"
	"github.com/package-dependency/go-resolver/internal/source"
	"golang.org/x/mod/module"
)

const defaultTimeout = 120 * time.Second

func main() {
	if len(os.Args) < 2 {
		printUsage()
		os.Exit(1)
	}

	switch os.Args[1] {
	case "resolve":
		runResolve(os.Args[2:])
	case "list":
		runList(os.Args[2:])
	default:
		printUsage()
		os.Exit(1)
	}
}

func printUsage() {
	fmt.Fprintln(os.Stderr, "usage:")
	fmt.Fprintln(os.Stderr, "  go_resolver resolve <module> <version> [--format graph|full] [--pretty]")
	fmt.Fprintln(os.Stderr, "  go_resolver list <module> <version> [--json] [--pretty]")
}

func newGraphResolver(timeout time.Duration) *resolver.Resolver {
	client := &http.Client{Timeout: timeout}
	proxyBaseURL := os.Getenv("GO_PROXY_BASE_URL")
	modSource := source.NewCachingSource(source.NewProxySource(client, proxyBaseURL))
	return resolver.New(modSource)
}

func resolveModule(target module.Version, timeout time.Duration) (*resolver.ResolveResult, error) {
	graphResolver := newGraphResolver(timeout)
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()
	return graphResolver.Resolve(ctx, target)
}

func emitJSON(payload any, pretty bool) {
	encoder := json.NewEncoder(os.Stdout)
	if pretty {
		encoder.SetIndent("", "  ")
	}
	if err := encoder.Encode(payload); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func runResolve(args []string) {
	if len(args) < 2 {
		printUsage()
		os.Exit(1)
	}

	resolveFlags := flag.NewFlagSet("resolve", flag.ExitOnError)
	format := resolveFlags.String("format", "graph", "output format: graph or full")
	pretty := resolveFlags.Bool("pretty", false, "pretty-print JSON output")
	if err := resolveFlags.Parse(args[2:]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}

	result, err := resolveModule(module.Version{Path: args[0], Version: args[1]}, defaultTimeout)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}

	payload, err := output.Build(result, *format)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}

	emitJSON(payload, *pretty)
}

func runList(args []string) {
	if len(args) < 2 {
		printUsage()
		os.Exit(1)
	}

	listFlags := flag.NewFlagSet("list", flag.ExitOnError)
	jsonOutput := listFlags.Bool("json", false, "emit structured JSON output")
	pretty := listFlags.Bool("pretty", false, "pretty-print JSON output")
	if err := listFlags.Parse(args[2:]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}

	result, err := resolveModule(module.Version{Path: args[0], Version: args[1]}, defaultTimeout)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}

	if *jsonOutput {
		emitJSON(output.BuildListPayload(result), *pretty)
		return
	}

	if _, err := fmt.Fprint(os.Stdout, output.BuildListText(result)); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
