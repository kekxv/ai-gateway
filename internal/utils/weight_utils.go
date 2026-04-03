package utils

import (
	"math/rand"
	"time"
)

func init() {
	rand.Seed(time.Now().UnixNano())
}

// WeightedRandomSelect selects an item based on weighted random selection
// Returns the index of the selected item
func WeightedRandomSelect(weights []int) int {
	if len(weights) == 0 {
		return -1
	}

	totalWeight := 0
	for _, w := range weights {
		totalWeight += w
	}

	if totalWeight == 0 {
		return 0
	}

	randomWeight := rand.Intn(totalWeight)

	for i, w := range weights {
		randomWeight -= w
		if randomWeight < 0 {
			return i
		}
	}

	return len(weights) - 1
}