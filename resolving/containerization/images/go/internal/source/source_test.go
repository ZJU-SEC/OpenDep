package source

import (
	"context"
	"errors"
	"testing"

	"github.com/package-dependency/go-resolver/internal/model"
	"golang.org/x/mod/module"
)

type stubModSource struct {
	meta *model.ModuleMeta
	err  error
}

func (s stubModSource) FetchGoMod(ctx context.Context, mod module.Version) (*model.ModuleMeta, error) {
	if s.err != nil {
		return nil, s.err
	}
	return s.meta, nil
}

func TestFallbackSourceUsesFallbackOnNotFound(t *testing.T) {
	expected := &model.ModuleMeta{ModulePath: "example.com/module"}
	source := NewFallbackSource(
		stubModSource{err: &Error{Code: ErrorNotFound, Message: "missing"}},
		stubModSource{meta: expected},
	)

	meta, err := source.FetchGoMod(context.Background(), module.Version{Path: "example.com/module", Version: "v1.0.0"})
	if err != nil {
		t.Fatalf("FetchGoMod returned error: %v", err)
	}
	if meta != expected {
		t.Fatalf("expected fallback meta pointer %p, got %p", expected, meta)
	}
}

func TestFallbackSourceKeepsPrimaryErrorForInvalidArgument(t *testing.T) {
	expectedErr := &Error{Code: ErrorInvalidArgument, Message: "bad input"}
	source := NewFallbackSource(
		stubModSource{err: expectedErr},
		stubModSource{meta: &model.ModuleMeta{ModulePath: "fallback"}},
	)

	_, err := source.FetchGoMod(context.Background(), module.Version{})
	if !errors.Is(err, expectedErr) {
		t.Fatalf("expected primary error %v, got %v", expectedErr, err)
	}
}
