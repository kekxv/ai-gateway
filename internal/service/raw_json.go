package service

import (
	"encoding/json"
	"errors"
)

var ErrInvalidJSONRequest = errors.New("request body must be a JSON object")

func parseRawRequestObject(rawBody []byte) (map[string]interface{}, error) {
	var obj map[string]interface{}
	if err := json.Unmarshal(rawBody, &obj); err != nil {
		return nil, err
	}
	if obj == nil {
		return nil, ErrInvalidJSONRequest
	}
	return obj, nil
}

func ExtractRawStringField(rawBody []byte, field string) (string, error) {
	obj, err := parseRawRequestObject(rawBody)
	if err != nil {
		return "", err
	}
	value, ok := obj[field].(string)
	if !ok || value == "" {
		return "", errors.New(field + " is required")
	}
	return value, nil
}

func ExtractRawBoolField(rawBody []byte, field string) bool {
	obj, err := parseRawRequestObject(rawBody)
	if err != nil {
		return false
	}
	value, _ := obj[field].(bool)
	return value
}

func replaceRawModel(rawBody []byte, upstreamModelName string) ([]byte, error) {
	obj, err := parseRawRequestObject(rawBody)
	if err != nil {
		return nil, err
	}
	obj["model"] = upstreamModelName
	return json.Marshal(obj)
}
