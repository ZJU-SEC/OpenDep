package models

type Module struct {
	Path    string `json:"Path" bson:"Path"`
	Version string `json:"Version" bson:"Version"`
}

type Dep struct {
	Path      string `json:"Path" bson:"Path"`
	Version   string `json:"Version" bson:"Version"`
	CacheTime string `json:"Timestamp" bson:"CacheTime"`
	Mod       struct {
		ModulePath   string   `bson:"ModulePath"`
		GoVersion    string   `bson:"GoVersion"`
		DirRequire   []Module `bson:"DirRequire"`
		IndirRequire []Module `bson:"IndirRequire"`
		Exclude      []Module `bson:"Exclude"`
		Replace      []string `bson:"Replace"`
		Retract      []string `bson:"Retract"`
	} `bson:"mod"`
	HasValidMod int    `bson:"HasValidMod"`
	ModFile     string `json:"modFile" bson:"ModFile"`
	IsOnPkg     bool   `bson:"IsOnPkg"`
}