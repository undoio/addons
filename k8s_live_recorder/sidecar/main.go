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

	uploaderStarted := make(chan struct{})
	controller.startUploaderLoop(ctx, uploaderStarted)
	<-uploaderStarted
	log.Println("S3 uploader started successfully")

	if err := controller.Run(ctx); err != nil && err != context.Canceled {
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
