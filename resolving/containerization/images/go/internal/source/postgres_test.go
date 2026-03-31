package source

import "testing"

func TestSanitizeQualifiedTableNameDefaultsToGoMetadata(t *testing.T) {
	got, err := sanitizeQualifiedTableName("")
	if err != nil {
		t.Fatalf("sanitizeQualifiedTableName returned error: %v", err)
	}
	if got != `"go_metadata"` {
		t.Fatalf("expected default table to be quoted go_metadata, got %q", got)
	}
}

func TestSanitizeQualifiedTableNameQuotesSchemaAndTable(t *testing.T) {
	got, err := sanitizeQualifiedTableName("public.go_metadata")
	if err != nil {
		t.Fatalf("sanitizeQualifiedTableName returned error: %v", err)
	}
	if got != `"public"."go_metadata"` {
		t.Fatalf("expected qualified table name to be quoted, got %q", got)
	}
}

func TestSanitizeQualifiedTableNameRejectsInvalidIdentifier(t *testing.T) {
	if _, err := sanitizeQualifiedTableName("go_metadata;drop table users"); err == nil {
		t.Fatal("expected invalid identifier error, got nil")
	}
}
