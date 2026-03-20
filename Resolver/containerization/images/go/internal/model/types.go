package model

import "golang.org/x/mod/module"

// ModuleMeta is the normalized in-memory representation of a parsed go.mod file.
type ModuleMeta struct {
	Requested        module.Version
	ModulePath       string
	GoVersion        string
	DirectRequires   []module.Version
	IndirectRequires []module.Version
	Excludes         map[module.Version]bool
	Replaces         map[module.Version]module.Version
	RawMod           string
}
