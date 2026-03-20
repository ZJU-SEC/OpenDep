package mvs

import (
	"fmt"

	"golang.org/x/mod/module"
)

// Graph implements an incremental version of the MVS algorithm, with the
// requirements pushed by the caller instead of pulled by the MVS traversal.
type Graph struct {
	cmp   func(v1, v2 string) int
	roots []module.Version

	required map[module.Version][]module.Version

	isRoot   map[module.Version]bool // contains true for roots and false for reachable non-roots
	selected map[string]string       // path → version
}

// NewGraph returns an incremental MVS graph containing only a set of root
// dependencies and using the given max function for version strings.
func NewGraph(cmp func(v1, v2 string) int, roots []module.Version) *Graph {
	g := &Graph{
		cmp:      cmp,
		roots:    roots[:len(roots):len(roots)],
		required: make(map[module.Version][]module.Version),
		isRoot:   make(map[module.Version]bool),
		selected: make(map[string]string),
	}

	for _, m := range roots {
		g.isRoot[m] = true
		if g.cmp(g.Selected(m.Path), m.Version) < 0 {
			g.selected[m.Path] = m.Version
		}
	}

	return g
}

// Require adds the information that module m requires all modules in reqs.
func (g *Graph) Require(m module.Version, reqs []module.Version) {
	if _, reachable := g.isRoot[m]; !reachable {
		panic(fmt.Sprintf("%v is not reachable from any root", m))
	}

	reqs = reqs[:len(reqs):len(reqs)]

	if _, dup := g.required[m]; dup {
		panic(fmt.Sprintf("requirements of %v have already been set", m))
	}
	g.required[m] = reqs

	for _, dep := range reqs {
		if _, ok := g.isRoot[dep]; !ok {
			g.isRoot[dep] = false
		}

		if g.cmp(g.Selected(dep.Path), dep.Version) < 0 {
			g.selected[dep.Path] = dep.Version
		}
	}
}

// RequiredBy returns the requirements passed to Require for m, if any.
func (g *Graph) RequiredBy(m module.Version) (reqs []module.Version, ok bool) {
	reqs, ok = g.required[m]
	return reqs, ok
}

// Selected returns the selected version of the given module path.
func (g *Graph) Selected(path string) (version string) {
	v, ok := g.selected[path]
	if !ok {
		return "none"
	}
	return v
}

// BuildList returns the selected versions of all modules present in the Graph.
func (g *Graph) BuildList() []module.Version {
	seenRoot := make(map[string]bool, len(g.roots))

	var list []module.Version
	for _, r := range g.roots {
		if seenRoot[r.Path] {
			continue
		}
		if v := g.Selected(r.Path); v != "none" {
			list = append(list, module.Version{Path: r.Path, Version: v})
		}
		seenRoot[r.Path] = true
	}
	uniqueRoots := list

	for path, version := range g.selected {
		if !seenRoot[path] {
			list = append(list, module.Version{Path: path, Version: version})
		}
	}
	module.Sort(list[len(uniqueRoots):])

	return list
}

// WalkBreadthFirst invokes f once, in breadth-first order, for each module version.
func (g *Graph) WalkBreadthFirst(f func(m module.Version)) {
	var queue []module.Version
	enqueued := make(map[module.Version]bool)
	for _, m := range g.roots {
		if m.Version != "none" {
			queue = append(queue, m)
			enqueued[m] = true
		}
	}

	for len(queue) > 0 {
		m := queue[0]
		queue = queue[1:]

		f(m)

		reqs, _ := g.RequiredBy(m)
		for _, r := range reqs {
			if !enqueued[r] && r.Version != "none" {
				queue = append(queue, r)
				enqueued[r] = true
			}
		}
	}
}
