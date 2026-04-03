package utils

import (
	"testing"
)

func TestWeightedRandomSelect(t *testing.T) {
	weights := []int{1, 2, 3}

	// Run multiple times to verify distribution
	counts := make(map[int]int)
	for i := 0; i < 10000; i++ {
		selected := WeightedRandomSelect(weights)
		counts[selected]++
	}

	// Index 2 should be selected about 50% of the time (weight 3 out of 6 total)
	if counts[2] < 4500 || counts[2] > 5500 {
		t.Errorf("Expected index 2 to be selected ~50%% of the time, got %d%%", counts[2]/100)
	}

	// Index 0 should be selected about 16.7% of the time (weight 1 out of 6 total)
	if counts[0] < 1200 || counts[0] > 2200 {
		t.Errorf("Expected index 0 to be selected ~16.7%% of the time, got %d%%", counts[0]/100)
	}
}

func TestWeightedRandomSelectEmpty(t *testing.T) {
	result := WeightedRandomSelect([]int{})
	if result != -1 {
		t.Errorf("Expected -1 for empty weights, got %d", result)
	}
}

func TestWeightedRandomSelectSingle(t *testing.T) {
	result := WeightedRandomSelect([]int{5})
	if result != 0 {
		t.Errorf("Expected 0 for single weight, got %d", result)
	}
}