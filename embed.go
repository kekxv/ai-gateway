package embedfs

import "embed"

//go:embed all:web/dist
var DistFS embed.FS
