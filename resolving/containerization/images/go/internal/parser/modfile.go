package parser

import (
	"fmt"

	"github.com/package-dependency/go-resolver/internal/model"
	"golang.org/x/mod/modfile"
	"golang.org/x/mod/module"
)

func ParseGoMod(requested module.Version, raw []byte) (*model.ModuleMeta, error) {
	parsed, err := modfile.Parse("go.mod", raw, nil)
	if err != nil {
		return nil, fmt.Errorf("parse go.mod: %w", err)
	}

	meta := &model.ModuleMeta{
		Requested:  requested,
		ModulePath: requested.Path,
		Excludes:   make(map[module.Version]bool),
		Replaces:   make(map[module.Version]module.Version),
		RawMod:     string(raw),
	}

	if parsed.Module != nil && parsed.Module.Mod.Path != "" {
		meta.ModulePath = parsed.Module.Mod.Path
	}
	if parsed.Go != nil {
		meta.GoVersion = parsed.Go.Version
	}

	for _, req := range parsed.Require {
		if req == nil {
			continue
		}
		if req.Indirect {
			meta.IndirectRequires = append(meta.IndirectRequires, req.Mod)
		} else {
			meta.DirectRequires = append(meta.DirectRequires, req.Mod)
		}
	}
	module.Sort(meta.DirectRequires)
	module.Sort(meta.IndirectRequires)

	for _, exclude := range parsed.Exclude {
		if exclude == nil {
			continue
		}
		meta.Excludes[exclude.Mod] = true
	}

	for _, replace := range parsed.Replace {
		if replace == nil {
			continue
		}
		meta.Replaces[replace.Old] = replace.New
	}

	return meta, nil
}
