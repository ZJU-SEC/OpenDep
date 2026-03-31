package resolver

import (
	"context"
	"fmt"
	"path/filepath"
	"strings"

	"github.com/package-dependency/go-resolver/internal/model"
	src "github.com/package-dependency/go-resolver/internal/source"
	"github.com/package-dependency/go-resolver/mvs"
	"golang.org/x/mod/module"
	"golang.org/x/mod/semver"
)

type ResolveResult struct {
	Target           module.Version
	Root             module.Version
	Graph            *mvs.Graph
	MetaByModule     map[module.Version]*model.ModuleMeta
	ActualByModule   map[module.Version]module.Version
	IndirectByModule map[module.Version]map[module.Version]bool
	ReplaceRules     map[module.Version]module.Version
	ExcludeRules     map[module.Version]bool
}

type Resolver struct {
	source src.ModSource
}

func New(source src.ModSource) *Resolver {
	return &Resolver{source: source}
}

func pruningForGoVersion(goVersion string) bool {
	if goVersion == "" {
		return false
	}
	return semver.Compare("v"+goVersion, "v1.17") >= 0
}

func cmpVersion(v1, v2 string) int {
	if v2 == "" {
		if v1 == "" {
			return 0
		}
		return -1
	}
	if v1 == "" {
		return 1
	}
	return semver.Compare(v1, v2)
}

func getRequiredList(owner module.Version, meta *model.ModuleMeta, excludeInfo map[module.Version]bool, indirectInfo map[module.Version]map[module.Version]bool) []module.Version {
	var list []module.Version
	indirect := make(map[module.Version]bool)

	for _, dependency := range meta.IndirectRequires {
		if !excludeInfo[dependency] {
			list = append(list, dependency)
			indirect[dependency] = true
		}
	}
	indirectInfo[owner] = indirect

	for _, dependency := range meta.DirectRequires {
		if !excludeInfo[dependency] {
			list = append(list, dependency)
		}
	}

	module.Sort(list)
	return list
}

func applyReplacement(mod module.Version, replace map[module.Version]module.Version) (module.Version, error) {
	if actual, ok := replace[mod]; ok {
		return validateReplacement(actual, mod)
	}
	if actual, ok := replace[module.Version{Path: mod.Path, Version: ""}]; ok {
		return validateReplacement(actual, mod)
	}
	return mod, nil
}

func validateReplacement(actual module.Version, original module.Version) (module.Version, error) {
	if actual.Version != "" {
		return actual, nil
	}
	if filepath.IsAbs(actual.Path) || strings.HasPrefix(actual.Path, "./") || strings.HasPrefix(actual.Path, "../") || actual.Path == "." || actual.Path == ".." {
		return module.Version{}, &Error{
			Code:      ErrorUnsupportedReplace,
			Message:   fmt.Sprintf("local path replace is not supported for %s@%s", original.Path, original.Version),
			Retryable: false,
		}
	}
	return module.Version{}, &Error{
		Code:      ErrorUnsupportedReplace,
		Message:   fmt.Sprintf("versionless replace target is not supported for %s@%s", original.Path, original.Version),
		Retryable: false,
	}
}

func mapSourceError(err error, mod module.Version) error {
	sourceErr, ok := err.(*src.Error)
	if !ok {
		return &Error{Code: ErrorDataUnavailable, Message: fmt.Sprintf("failed to fetch %s@%s", mod.Path, mod.Version), Retryable: true, Err: err}
	}

	switch sourceErr.Code {
	case src.ErrorInvalidArgument:
		return &Error{Code: ErrorInvalidArgument, Message: sourceErr.Message, Retryable: false, Err: err}
	case src.ErrorNotFound:
		return &Error{Code: ErrorVersionNotFound, Message: sourceErr.Message, Retryable: false, Err: err}
	case src.ErrorProtocol:
		return &Error{Code: ErrorProtocol, Message: sourceErr.Message, Retryable: false, Err: err}
	default:
		return &Error{Code: ErrorDataUnavailable, Message: sourceErr.Message, Retryable: true, Err: err}
	}
}

func (r *Resolver) Resolve(ctx context.Context, target module.Version) (*ResolveResult, error) {
	if target.Path == "" || target.Version == "" {
		return nil, &Error{Code: ErrorInvalidArgument, Message: "target module path and version are required", Retryable: false}
	}

	targetMeta, err := r.source.FetchGoMod(ctx, target)
	if err != nil {
		return nil, mapSourceError(err, target)
	}

	rootPath := targetMeta.ModulePath
	if rootPath == "" {
		rootPath = target.Path
	}
	rootGraphModule := module.Version{Path: rootPath, Version: ""}
	rootResolvedModule := module.Version{Path: rootPath, Version: target.Version}

	graph := mvs.NewGraph(cmpVersion, []module.Version{rootGraphModule})
	indirectInfo := make(map[module.Version]map[module.Version]bool)
	replaceInfo := targetMeta.Replaces
	excludeInfo := targetMeta.Excludes

	roots := getRequiredList(rootGraphModule, targetMeta, excludeInfo, indirectInfo)
	filteredRoots := make([]module.Version, 0, len(roots))
	for _, dependency := range roots {
		if dependency.Path != rootPath {
			filteredRoots = append(filteredRoots, dependency)
		}
	}
	module.Sort(filteredRoots)
	graph.Require(rootGraphModule, filteredRoots)

	result := &ResolveResult{
		Target:           target,
		Root:             rootResolvedModule,
		Graph:            graph,
		MetaByModule:     map[module.Version]*model.ModuleMeta{rootGraphModule: targetMeta},
		ActualByModule:   map[module.Version]module.Version{rootGraphModule: target},
		IndirectByModule: indirectInfo,
		ReplaceRules:     replaceInfo,
		ExcludeRules:     excludeInfo,
	}

	expanded := make(map[module.Version]bool)
	mainPruning := pruningForGoVersion(targetMeta.GoVersion)

	loadOne := func(mod module.Version) ([]module.Version, bool, error) {
		actual, replaceErr := applyReplacement(mod, replaceInfo)
		if replaceErr != nil {
			return nil, false, replaceErr
		}

		currentMeta, ok := result.MetaByModule[mod]
		if !ok {
			currentMeta, err = r.source.FetchGoMod(ctx, actual)
			if err != nil {
				return nil, false, mapSourceError(err, actual)
			}
			result.MetaByModule[mod] = currentMeta
			result.ActualByModule[mod] = actual
		}

		if reqs, loaded := graph.RequiredBy(mod); loaded {
			return reqs[:len(reqs):len(reqs)], pruningForGoVersion(currentMeta.GoVersion), nil
		}

		required := getRequiredList(mod, currentMeta, excludeInfo, indirectInfo)
		graph.Require(mod, required)
		return required, pruningForGoVersion(currentMeta.GoVersion), nil
	}

	var enqueue func(mod module.Version, pruning bool) error
	enqueue = func(mod module.Version, pruning bool) error {
		if mod.Version == "none" {
			return nil
		}
		if !pruning {
			if expanded[mod] {
				return nil
			}
		}

		required, currentPruning, loadErr := loadOne(mod)
		if loadErr != nil {
			return loadErr
		}

		if !pruning || !currentPruning {
			nextPruning := currentPruning
			if !pruning {
				nextPruning = false
			}
			expanded[mod] = true
			for _, dependency := range required {
				if err := enqueue(dependency, nextPruning); err != nil {
					return err
				}
			}
		}
		return nil
	}

	for _, dependency := range filteredRoots {
		if err := enqueue(dependency, mainPruning); err != nil {
			return nil, err
		}
	}

	return result, nil
}
