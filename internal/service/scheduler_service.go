package service

import (
	"context"
	"log"
	"sync"
	"time"
)

// SchedulerService handles periodic model sync scheduling
type SchedulerService struct {
	syncService   *ModelSyncService
	providerRepo  interface{} // Will be used for future enhancements
	interval      time.Duration
	initialDelay  time.Duration
	ticker        *time.Ticker
	stopChan      chan struct{}
	wg            sync.WaitGroup
	mu            sync.Mutex
	running       bool
}

// NewSchedulerService creates a new scheduler service
func NewSchedulerService(
	syncService *ModelSyncService,
	syncInterval time.Duration,
	initialDelay time.Duration,
) *SchedulerService {
	return &SchedulerService{
		syncService:  syncService,
		interval:     syncInterval,
		initialDelay: initialDelay,
		stopChan:     make(chan struct{}),
	}
}

// Start starts the scheduler
func (s *SchedulerService) Start(ctx context.Context) {
	s.mu.Lock()
	if s.running {
		s.mu.Unlock()
		return
	}
	s.running = true
	s.mu.Unlock()

	log.Println("[Scheduler] Starting model sync scheduler...")

	// Wait for initial delay
	if s.initialDelay > 0 {
		log.Printf("[Scheduler] Waiting %v before first sync...", s.initialDelay)
		time.Sleep(s.initialDelay)
	}

	// Run initial sync
	s.runSync(ctx)

	// Start ticker
	s.ticker = time.NewTicker(s.interval)

	s.wg.Add(1)
	go func() {
		defer s.wg.Done()
		for {
			select {
			case <-s.ticker.C:
				s.runSync(ctx)
			case <-s.stopChan:
				log.Println("[Scheduler] Stopping...")
				return
			case <-ctx.Done():
				log.Println("[Scheduler] Context cancelled, stopping...")
				return
			}
		}
	}()

	log.Printf("[Scheduler] Scheduler started with interval %v", s.interval)
}

// Stop stops the scheduler
func (s *SchedulerService) Stop() {
	s.mu.Lock()
	if !s.running {
		s.mu.Unlock()
		return
	}
	s.running = false
	s.mu.Unlock()

	close(s.stopChan)
	if s.ticker != nil {
		s.ticker.Stop()
	}
	s.wg.Wait()
	log.Println("[Scheduler] Scheduler stopped")
}

// runSync executes a sync cycle
func (s *SchedulerService) runSync(ctx context.Context) {
	log.Println("[Scheduler] Starting model sync cycle...")
	startTime := time.Now()

	results := s.syncService.SyncAllProviders(ctx)

	for _, result := range results {
		if result.Error != nil {
			log.Printf("[Scheduler] Provider %d (%s): ERROR - %v",
				result.ProviderID, result.ProviderName, result.Error)
		} else {
			log.Printf("[Scheduler] Provider %d (%s): created=%d, routes=%d, removed=%d, fetched=%d",
				result.ProviderID, result.ProviderName,
				result.ModelsCreated, result.RoutesCreated,
				result.ModelsRemoved, result.TotalFetched)
		}
	}

	log.Printf("[Scheduler] Sync cycle completed in %v", time.Since(startTime))
}