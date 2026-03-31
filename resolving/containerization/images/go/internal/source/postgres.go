package source

import (
	"context"
	"errors"
	"fmt"
	"regexp"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/package-dependency/go-resolver/internal/model"
	"github.com/package-dependency/go-resolver/internal/parser"
	"golang.org/x/mod/module"
)

const defaultIndexTableName = "go_metadata"

var postgresIdentifierPattern = regexp.MustCompile(`^[A-Za-z_][A-Za-z0-9_]*$`)

type PostgresSource struct {
	pool        *pgxpool.Pool
	selectQuery string
}

func NewPostgresSource(ctx context.Context, dsn string, tableName string) (*PostgresSource, error) {
	resolvedDSN := strings.TrimSpace(dsn)
	if resolvedDSN == "" {
		return nil, errors.New("GO_INDEX_DSN is required when GO_METADATA_MODE=indexed")
	}

	qualifiedTable, err := sanitizeQualifiedTableName(tableName)
	if err != nil {
		return nil, err
	}

	pool, err := pgxpool.New(ctx, resolvedDSN)
	if err != nil {
		return nil, fmt.Errorf("connect postgres index: %w", err)
	}

	return &PostgresSource{
		pool:        pool,
		selectQuery: fmt.Sprintf("SELECT raw_mod FROM %s WHERE module_path = $1 AND version = $2 LIMIT 1", qualifiedTable),
	}, nil
}

func (s *PostgresSource) FetchGoMod(ctx context.Context, mod module.Version) (*model.ModuleMeta, error) {
	if mod.Path == "" || mod.Version == "" {
		return nil, &Error{Code: ErrorInvalidArgument, Message: "module path and version are required"}
	}

	var rawMod string
	err := s.pool.QueryRow(ctx, s.selectQuery, mod.Path, mod.Version).Scan(&rawMod)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, &Error{Code: ErrorNotFound, Message: fmt.Sprintf("module version not found: %s@%s", mod.Path, mod.Version)}
		}
		return nil, &Error{Code: ErrorDataSourceUnavailable, Message: "postgres index query failed", Err: err}
	}

	meta, err := parser.ParseGoMod(mod, []byte(rawMod))
	if err != nil {
		return nil, &Error{Code: ErrorProtocol, Message: "failed to parse stored go.mod content", Err: err}
	}
	return meta, nil
}

func sanitizeQualifiedTableName(tableName string) (string, error) {
	trimmed := strings.TrimSpace(tableName)
	if trimmed == "" {
		trimmed = defaultIndexTableName
	}

	parts := strings.Split(trimmed, ".")
	quoted := make([]string, 0, len(parts))
	for _, part := range parts {
		if !postgresIdentifierPattern.MatchString(part) {
			return "", fmt.Errorf("invalid PostgreSQL table identifier: %q", tableName)
		}
		quoted = append(quoted, `"`+part+`"`)
	}
	return strings.Join(quoted, "."), nil
}
