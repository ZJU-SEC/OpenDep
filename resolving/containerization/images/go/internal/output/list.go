package output

import (
	"bytes"
	"fmt"
	"text/tabwriter"

	"github.com/package-dependency/go-resolver/internal/resolver"
)

type listEntry struct {
	Path           string `json:"path"`
	Version        string `json:"version,omitempty"`
	ReplacePath    string `json:"replace_path,omitempty"`
	ReplaceVersion string `json:"replace_version,omitempty"`
}

func BuildListPayload(result *resolver.ResolveResult) map[string]any {
	buildList := result.Graph.BuildList()
	entries := make([]listEntry, 0, max(len(buildList)-1, 0))
	for _, mod := range buildList[1:] {
		entry := listEntry{Path: mod.Path, Version: mod.Version}
		if replacement, ok := lookupReplacement(result, mod); ok {
			entry.ReplacePath = replacement.Path
			entry.ReplaceVersion = replacement.Version
		}
		entries = append(entries, entry)
	}

	payload := map[string]any{
		"root": map[string]any{
			"path":    result.Root.Path,
			"version": result.Root.Version,
		},
		"entries": entries,
		"metrics": map[string]any{
			"entry_count": len(entries),
		},
	}
	if result.Target.Path != "" && (result.Target.Path != result.Root.Path || result.Target.Version != result.Root.Version) {
		payload["requested"] = map[string]any{
			"path":    result.Target.Path,
			"version": result.Target.Version,
		}
	}
	return payload
}

func BuildListText(result *resolver.ResolveResult) string {
	buildList := result.Graph.BuildList()
	if len(buildList) == 0 {
		return ""
	}

	var buffer bytes.Buffer
	writer := tabwriter.NewWriter(&buffer, 0, 0, 2, ' ', 0)

	fmt.Fprintf(writer, "%s\t%s", result.Root.Path, result.Root.Version)
	if result.Target.Path != "" && (result.Target.Path != result.Root.Path || result.Target.Version != result.Root.Version) {
		fmt.Fprintf(writer, "\t(requested %s %s)", result.Target.Path, result.Target.Version)
	}
	fmt.Fprintln(writer)

	for _, mod := range buildList[1:] {
		fmt.Fprintf(writer, "  %s\t%s", mod.Path, mod.Version)
		if replacement, ok := lookupReplacement(result, mod); ok {
			fmt.Fprintf(writer, "\t=> %s", replacement.Path)
			if replacement.Version != "" {
				fmt.Fprintf(writer, " %s", replacement.Version)
			}
		}
		fmt.Fprintln(writer)
	}

	_ = writer.Flush()
	return buffer.String()
}

func max(left, right int) int {
	if left > right {
		return left
	}
	return right
}
