package service

import (
	"encoding/json"
	"testing"
)

func TestReplaceRawModel_PreservesUnknownFields(t *testing.T) {
	raw := []byte(`{
		"model" : "alias-model",
		"messages": [{"role": "user", "content": "hi"}],
		"future_options": {"new_param": true},
		"stream": true
	}`)

	replaced, err := replaceRawModel(raw, "upstream-model")
	if err != nil {
		t.Fatalf("replaceRawModel failed: %v", err)
	}

	var obj map[string]interface{}
	if err := json.Unmarshal(replaced, &obj); err != nil {
		t.Fatalf("replacement is not valid json: %v", err)
	}

	if obj["model"] != "upstream-model" {
		t.Fatalf("expected model to be replaced, got %v", obj["model"])
	}
	if _, ok := obj["future_options"].(map[string]interface{}); !ok {
		t.Fatalf("expected unknown fields to be preserved, got %v", obj)
	}
	if obj["stream"] != true {
		t.Fatalf("expected stream field to be preserved")
	}
}

func TestReplaceRawModel_RejectsNonObject(t *testing.T) {
	if _, err := replaceRawModel([]byte(`[]`), "upstream-model"); err == nil {
		t.Fatal("expected non-object json to fail")
	}
}
