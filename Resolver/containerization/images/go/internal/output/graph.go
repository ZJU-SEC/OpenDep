package output

import (
	"fmt"
	"sort"

	"github.com/package-dependency/go-resolver/internal/resolver"
	"golang.org/x/mod/module"
)

type graphNode struct {
	ID            string `json:"id"`
	Path          string `json:"path"`
	Version       string `json:"version,omitempty"`
	Main          bool   `json:"main,omitempty"`
	ActualPath    string `json:"actual_path,omitempty"`
	ActualVersion string `json:"actual_version,omitempty"`
}

type graphEdge struct {
	From     string `json:"from"`
	To       string `json:"to"`
	Indirect bool   `json:"indirect,omitempty"`
}

type buildItem struct {
	Path           string `json:"path"`
	Version        string `json:"version,omitempty"`
	ReplacePath    string `json:"replace_path,omitempty"`
	ReplaceVersion string `json:"replace_version,omitempty"`
}

type replaceItem struct {
	FromPath    string `json:"from_path"`
	FromVersion string `json:"from_version,omitempty"`
	ToPath      string `json:"to_path"`
	ToVersion   string `json:"to_version,omitempty"`
}

func Build(result *resolver.ResolveResult, format string) (map[string]any, error) {
	if format != "graph" && format != "full" {
		return nil, fmt.Errorf("unsupported output format: %s", format)
	}

	rootGraphModule := module.Version{Path: result.Root.Path, Version: ""}
	rootID := nodeID(result, rootGraphModule)

	visited := map[module.Version]bool{}
	modules := []module.Version{rootGraphModule}
	result.Graph.WalkBreadthFirst(func(mod module.Version) {
		if visited[mod] {
			return
		}
		visited[mod] = true
		if mod != rootGraphModule {
			modules = append(modules, mod)
		}
	})

	sort.Slice(modules[1:], func(i, j int) bool {
		left := modules[i+1]
		right := modules[j+1]
		if left.Path == right.Path {
			return left.Version < right.Version
		}
		return left.Path < right.Path
	})

	nodes := make([]graphNode, 0, len(modules))
	for _, mod := range modules {
		actual := result.ActualByModule[mod]
		node := graphNode{
			ID:      nodeID(result, mod),
			Path:    displayPath(result, mod),
			Version: displayVersion(result, mod),
			Main:    mod == rootGraphModule,
		}
		if actual.Path != "" && (actual.Path != node.Path || actual.Version != node.Version) {
			node.ActualPath = actual.Path
			node.ActualVersion = actual.Version
		}
		nodes = append(nodes, node)
	}

	edges := make([]graphEdge, 0)
	for _, mod := range modules {
		reqs, ok := result.Graph.RequiredBy(mod)
		if !ok {
			continue
		}
		for _, dep := range reqs {
			indirect := false
			if info, exists := result.IndirectByModule[mod]; exists {
				indirect = info[dep]
			}
			edges = append(edges, graphEdge{
				From:     nodeID(result, mod),
				To:       nodeID(result, dep),
				Indirect: indirect,
			})
		}
	}
	sort.Slice(edges, func(i, j int) bool {
		if edges[i].From == edges[j].From {
			return edges[i].To < edges[j].To
		}
		return edges[i].From < edges[j].From
	})

	payload := map[string]any{
		"root": map[string]any{
			"id":      rootID,
			"path":    result.Root.Path,
			"version": result.Root.Version,
		},
		"nodes": nodes,
		"edges": edges,
		"semantics": map[string]any{
			"resolver": "mvs",
			"target": map[string]string{
				"path":    result.Target.Path,
				"version": result.Target.Version,
			},
		},
		"metrics": map[string]any{
			"node_count": len(nodes),
			"edge_count": len(edges),
		},
	}

	if format == "full" {
		payload["build_list"] = buildList(result)
		payload["replacements"] = replacements(result)
	}

	return payload, nil
}

func buildList(result *resolver.ResolveResult) []buildItem {
	buildList := result.Graph.BuildList()
	items := make([]buildItem, 0, len(buildList))
	for _, mod := range buildList {
		item := buildItem{Path: mod.Path, Version: mod.Version}
		if mod.Path == result.Root.Path && mod.Version == "" {
			item.Version = result.Root.Version
		}
		if replacement, ok := lookupReplacement(result, mod); ok {
			item.ReplacePath = replacement.Path
			item.ReplaceVersion = replacement.Version
		}
		items = append(items, item)
	}
	return items
}

func replacements(result *resolver.ResolveResult) []replaceItem {
	items := make([]replaceItem, 0, len(result.ReplaceRules))
	for from, to := range result.ReplaceRules {
		items = append(items, replaceItem{
			FromPath:    from.Path,
			FromVersion: from.Version,
			ToPath:      to.Path,
			ToVersion:   to.Version,
		})
	}
	sort.Slice(items, func(i, j int) bool {
		if items[i].FromPath == items[j].FromPath {
			return items[i].FromVersion < items[j].FromVersion
		}
		return items[i].FromPath < items[j].FromPath
	})
	return items
}

func lookupReplacement(result *resolver.ResolveResult, mod module.Version) (module.Version, bool) {
	if replacement, ok := result.ReplaceRules[mod]; ok {
		return replacement, true
	}
	if replacement, ok := result.ReplaceRules[module.Version{Path: mod.Path, Version: ""}]; ok {
		return replacement, true
	}
	return module.Version{}, false
}

func nodeID(result *resolver.ResolveResult, mod module.Version) string {
	path := displayPath(result, mod)
	version := displayVersion(result, mod)
	return fmt.Sprintf("go:%s@%s", path, version)
}

func displayPath(result *resolver.ResolveResult, mod module.Version) string {
	if mod.Path == result.Root.Path && mod.Version == "" {
		return result.Root.Path
	}
	return mod.Path
}

func displayVersion(result *resolver.ResolveResult, mod module.Version) string {
	if mod.Path == result.Root.Path && mod.Version == "" {
		return result.Root.Version
	}
	return mod.Version
}
