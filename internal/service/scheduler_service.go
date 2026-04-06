package service

import (
	"context"
	"log"
	"sync"
	"time"
)

// ScheduledTask defines the interface for tasks that can be scheduled
type ScheduledTask interface {
	Name() string
	Run(ctx context.Context)
}

// SchedulerService handles periodic task scheduling
type SchedulerService struct {
	tasks       []ScheduledTask
	interval    time.Duration
	initialDelay time.Duration
	ticker      *time.Ticker
	stopChan    chan struct{}
	wg          sync.WaitGroup
	mu          sync.Mutex
	running     bool
}

// NewSchedulerService creates a new scheduler service
func NewSchedulerService(
	syncInterval time.Duration,
	initialDelay time.Duration,
) *SchedulerService {
	return &SchedulerService{
		tasks:        []ScheduledTask{},
		interval:     syncInterval,
		initialDelay: initialDelay,
		stopChan:     make(chan struct{}),
	}
}

// AddTask adds a task to the scheduler
func (s *SchedulerService) AddTask(task ScheduledTask) {
	s.mu.Lock()
	s.tasks = append(s.tasks, task)
	s.mu.Unlock()
}

// Start starts the scheduler (non-blocking, runs sync in background)
func (s *SchedulerService) Start(ctx context.Context) {
	s.mu.Lock()
	if s.running {
		s.mu.Unlock()
		return
	}
	s.running = true
	s.mu.Unlock()

	s.ticker = time.NewTicker(s.interval)

	s.wg.Add(1)
	go func() {
		defer s.wg.Done()

		// Wait for initial delay (async)
		if s.initialDelay > 0 {
			log.Printf("[Scheduler] Waiting %v before first sync...", s.initialDelay)
			time.Sleep(s.initialDelay)
		}

		// Run initial sync (async)
		s.runSync(ctx)

		// Start periodic sync loop
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

// runSync executes all scheduled tasks
func (s *SchedulerService) runSync(ctx context.Context) {
	s.mu.Lock()
	tasks := s.tasks
	s.mu.Unlock()

	if len(tasks) == 0 {
		log.Println("[Scheduler] No tasks to run")
		return
	}

	log.Println("[Scheduler] Starting scheduled tasks cycle...")
	startTime := time.Now()

	for _, task := range tasks {
		log.Printf("[Scheduler] Running task: %s", task.Name())
		task.Run(ctx)
	}

	log.Printf("[Scheduler] All tasks completed in %v", time.Since(startTime))
}