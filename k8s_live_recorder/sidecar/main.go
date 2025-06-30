// Package main implements a wrapper application that records
// application processes using Undo's LiveRecorder tool from
// within a Kubernetes sidecar container.
package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"
)

const (
	liveRecordPath = "/undo/live-record"
	undolrPath     = "/undo/undolr"
	recordingsDir  = "/recordings"
)

func main() {
	log.Println("Starting Undo LiveRecorder sidecar")

	// set up signal handling for graceful shutdown
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer stop()

	cfg, err := loadConfig()
	if err != nil {
		log.Fatalf("Failed to load configuration: %v", err)
	}

	if err := validateEnvironment(); err != nil {
		log.Fatalf("Environment validation failed: %v", err)
	}

	controller, err := newRecorderController(cfg)
	if err != nil {
		log.Fatalf("Failed to initialize recorder controller: %v", err)
	}

	targetPID, err := findTargetProcess(cfg.AppProcessName)
	if err != nil {
		log.Fatalf("Failed to find target process: %v", err)
	}
	log.Printf("Found target process %s with PID %d", cfg.AppProcessName, targetPID)

	if err := copyTargetExecutable(targetPID); err != nil {
		log.Fatalf("Failed to copy target executable: %v", err)
	}

	if err := copySharedLibraries(targetPID); err != nil {
		log.Fatalf("Failed to copy shared libraries: %v", err)
	}

	uploaderStarted := make(chan struct{})
    controller.startUploaderLoop(ctx, uploaderStarted)
    <-uploaderStarted
    log.Println("S3 uploader started successfully")

	if err := controller.Run(ctx, targetPID); err != nil && err != context.Canceled {
		log.Fatalf("Controller execution failed: %v", err)
	}

	log.Println("Sidecar shutting down gracefully")
}

func validateEnvironment() error {
	if _, err := os.Stat(liveRecordPath); err != nil {
		return wrapErr("checking live-record binary", err)
	}

	if _, err := os.Stat(undolrPath); err != nil {
		return wrapErr("checking undolr directory", err)
	}

	if err := os.MkdirAll(recordingsDir, 0755); err != nil {
		return wrapErr("creating recordings directory", err)
	}

	if err := os.MkdirAll("/tmp", 0755); err != nil {
		return wrapErr("creating tmp directory", err)
	}

	return nil
}
