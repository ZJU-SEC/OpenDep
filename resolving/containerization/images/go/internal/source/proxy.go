package source

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/package-dependency/go-resolver/internal/model"
	"github.com/package-dependency/go-resolver/internal/parser"
	"golang.org/x/mod/module"
)

const defaultProxyBaseURL = "https://proxy.golang.org"

type ProxySource struct {
	baseURL string
	client  *http.Client
}

func NewProxySource(client *http.Client, baseURL string) *ProxySource {
	if client == nil {
		client = &http.Client{Timeout: 120 * time.Second}
	}
	if baseURL == "" {
		baseURL = defaultProxyBaseURL
	}
	return &ProxySource{
		baseURL: strings.TrimRight(baseURL, "/"),
		client:  client,
	}
}

func (s *ProxySource) FetchGoMod(ctx context.Context, mod module.Version) (*model.ModuleMeta, error) {
	if mod.Path == "" || mod.Version == "" {
		return nil, &Error{Code: ErrorInvalidArgument, Message: "module path and version are required"}
	}

	escapedPath, err := module.EscapePath(mod.Path)
	if err != nil {
		return nil, &Error{Code: ErrorInvalidArgument, Message: "invalid module path", Err: err}
	}
	escapedVersion, err := module.EscapeVersion(mod.Version)
	if err != nil {
		return nil, &Error{Code: ErrorInvalidArgument, Message: "invalid module version", Err: err}
	}

	requestURL := fmt.Sprintf("%s/%s/@v/%s.mod", s.baseURL, escapedPath, escapedVersion)
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, requestURL, nil)
	if err != nil {
		return nil, &Error{Code: ErrorInvalidArgument, Message: "failed to create request", Err: err}
	}
	request.Header.Set("User-Agent", "package-dependency-go-resolver/0.1")

	response, err := s.client.Do(request)
	if err != nil {
		return nil, &Error{Code: ErrorDataSourceUnavailable, Message: "go proxy request failed", Err: err}
	}
	defer response.Body.Close()

	body, err := io.ReadAll(response.Body)
	if err != nil {
		return nil, &Error{Code: ErrorDataSourceUnavailable, Message: "failed to read go proxy response", Err: err}
	}

	if response.StatusCode == http.StatusNotFound {
		return nil, &Error{Code: ErrorNotFound, Message: fmt.Sprintf("module version not found: %s@%s", mod.Path, mod.Version)}
	}
	if response.StatusCode != http.StatusOK {
		return nil, &Error{
			Code:    ErrorDataSourceUnavailable,
			Message: fmt.Sprintf("go proxy returned status %d for %s@%s", response.StatusCode, mod.Path, mod.Version),
		}
	}

	meta, err := parser.ParseGoMod(mod, body)
	if err != nil {
		return nil, &Error{Code: ErrorProtocol, Message: "failed to parse go.mod content", Err: err}
	}
	return meta, nil
}
