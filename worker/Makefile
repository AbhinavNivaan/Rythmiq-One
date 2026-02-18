# =============================================================================
# Rythmiq Worker - Makefile
# =============================================================================
# Production build targets for the pre-baked Docker image.
# =============================================================================

.PHONY: build push test clean help

# Configuration
IMAGE_NAME ?= rythmiq/worker
TAG ?= production
PLATFORM ?= linux/amd64
REGISTRY ?= docker.io

FULL_IMAGE = $(REGISTRY)/$(IMAGE_NAME):$(TAG)

# Default target
help:
	@echo "Rythmiq Worker - Build Targets"
	@echo ""
	@echo "  make build     Build production image (linux/amd64)"
	@echo "  make push      Build and push to registry"
	@echo "  make test      Run smoke test on built image"
	@echo "  make clean     Remove local images"
	@echo "  make size      Show image size"
	@echo ""
	@echo "Configuration:"
	@echo "  IMAGE_NAME=$(IMAGE_NAME)"
	@echo "  TAG=$(TAG)"
	@echo "  REGISTRY=$(REGISTRY)"

# Build production image
build:
	@echo "Building $(FULL_IMAGE) for $(PLATFORM)..."
	docker buildx build \
		--platform $(PLATFORM) \
		--load \
		-f Dockerfile.production \
		-t $(FULL_IMAGE) \
		.

# Build and push to registry
push:
	@echo "Building and pushing $(FULL_IMAGE)..."
	docker buildx build \
		--platform $(PLATFORM) \
		--push \
		-f Dockerfile.production \
		-t $(FULL_IMAGE) \
		.

# Smoke test
test:
	@echo "Running smoke test..."
	@docker run --rm --platform $(PLATFORM) $(FULL_IMAGE) python -c "\
		from paddleocr import PaddleOCR; \
		ocr = PaddleOCR(use_angle_cls=True, lang='en'); \
		print('OK: PaddleOCR initialized from cache'); \
	"

# Show image size
size:
	@docker image inspect $(FULL_IMAGE) --format='Image size: {{.Size}}' | \
		awk '{printf "%.0f MB\n", $$3/1024/1024}'

# Clean up
clean:
	docker rmi $(FULL_IMAGE) 2>/dev/null || true
	docker rmi $(IMAGE_NAME):$(TAG) 2>/dev/null || true
