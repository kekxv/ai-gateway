package service

import (
	"context"
	"log"
	"time"

	"github.com/kekxv/ai-gateway/internal/repository"
)

// LogCleanupService handles periodic cleanup of old log details
type LogCleanupService struct {
	logDetailRepo   *repository.LogDetailRepository
	detailRetention time.Duration
}

// NewLogCleanupService creates a new log cleanup service
func NewLogCleanupService(
	logDetailRepo *repository.LogDetailRepository,
	detailRetention time.Duration,
) *LogCleanupService {
	return &LogCleanupService{
		logDetailRepo:   logDetailRepo,
		detailRetention: detailRetention,
	}
}

// Name returns the task name for scheduler
func (s *LogCleanupService) Name() string {
	return "log_cleanup"
}

// Run executes the cleanup task (implements ScheduledTask interface)
func (s *LogCleanupService) Run(ctx context.Context) {
	s.Cleanup(ctx)
}

// Cleanup removes old LogDetail records (request/response bodies)
// This reduces disk usage while keeping Log records for statistics
func (s *LogCleanupService) Cleanup(ctx context.Context) {
	now := time.Now()
	before := now.Add(-s.detailRetention)

	log.Printf("[LogCleanup] Cleaning up LogDetails older than %v (%v ago)", before, s.detailRetention)

	// Delete LogDetail records older than retention period
	// This removes the large request/response bodies but keeps Log records
	if err := s.logDetailRepo.Cleanup(ctx, before); err != nil {
		log.Printf("[LogCleanup] Error cleaning up LogDetails: %v", err)
		return
	}

	log.Printf("[LogCleanup] LogDetails cleanup completed successfully")
}