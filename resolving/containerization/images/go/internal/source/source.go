package source

import (
	"context"
	"fmt"
	"sync"

	"github.com/package-dependency/go-resolver/internal/model"
	"golang.org/x/mod/module"
)

type ErrorCode string

const (
	ErrorInvalidArgument       ErrorCode = "INVALID_ARGUMENT"
	ErrorNotFound              ErrorCode = "NOT_FOUND"
	ErrorDataSourceUnavailable ErrorCode = "DATA_SOURCE_UNAVAILABLE"
	ErrorProtocol              ErrorCode = "PROTOCOL_ERROR"
)

type Error struct {
	Code    ErrorCode
	Message string
	Err     error
}

func (e *Error) Error() string {
	if e == nil {
		return ""
	}
	if e.Err == nil {
		return fmt.Sprintf("%s: %s", e.Code, e.Message)
	}
	return fmt.Sprintf("%s: %s: %v", e.Code, e.Message, e.Err)
}

func (e *Error) Unwrap() error {
	if e == nil {
		return nil
	}
	return e.Err
}

type ModSource interface {
	FetchGoMod(ctx context.Context, mod module.Version) (*model.ModuleMeta, error)
}

type CachingSource struct {
	inner ModSource
	mu    sync.Mutex
	cache map[module.Version]*model.ModuleMeta
}

func NewCachingSource(inner ModSource) *CachingSource {
	return &CachingSource{
		inner: inner,
		cache: make(map[module.Version]*model.ModuleMeta),
	}
}

func (s *CachingSource) FetchGoMod(ctx context.Context, mod module.Version) (*model.ModuleMeta, error) {
	s.mu.Lock()
	cached := s.cache[mod]
	s.mu.Unlock()
	if cached != nil {
		return cached, nil
	}

	meta, err := s.inner.FetchGoMod(ctx, mod)
	if err != nil {
		return nil, err
	}

	s.mu.Lock()
	s.cache[mod] = meta
	s.mu.Unlock()
	return meta, nil
}
