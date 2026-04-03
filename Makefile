.PHONY: build run test clean

build:
	cd ai-gateway-go && go build -o bin/ai-gateway ./cmd/server

run:
	cd ai-gateway-go && go run ./cmd/server

test:
	cd ai-gateway-go && go test -v ./...

clean:
	rm -rf ai-gateway-go/bin

deps:
	cd ai-gateway-go && go mod download && go mod tidy

docker-build:
	docker build -t ai-gateway:latest ./ai-gateway-go

docker-run:
	docker run -p 3000:3000 -v $(PWD)/ai-gateway.db:/app/ai-gateway.db ai-gateway:latest