// recorder.go implements the main controller logic for managing recording processes
// in a Kubernetes sidecar container. It handles annotations for starting and stopping
// recordings, manages the recording process, and triggers uploads to S3.
package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"sync"
	"syscall"
	"time"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
)

// Annotation keys
const (
	liveRecordAnnotation = "undo.io/live-record" // annotation for start and stop
	statusAnnotation     = "undo.io/status"      // annotation for status
	pollInterval         = 5 * time.Second
)

// Status enum values
type Status string

const (
	StatusBusy Status = "busy"
	StatusIdle Status = "idle"
)

type RecorderController struct {
	clientset        *kubernetes.Clientset
	config           *Config
	recordingProcess *exec.Cmd
	recordingLock    sync.Mutex
}

func newRecorderController(cfg *Config) (*RecorderController, error) {
	k8sConfig, err := rest.InClusterConfig()
	if err != nil {
		return nil, wrapErr("creating in-cluster config", err)
	}

	clientset, err := kubernetes.NewForConfig(k8sConfig)
	if err != nil {
		return nil, wrapErr("creating Kubernetes clientset", err)
	}

	return &RecorderController{
		clientset: clientset,
		config:    cfg,
	}, nil
}

func (rc *RecorderController) Run(ctx context.Context, targetPID int) error {
	log.Println("Starting recorder controller loop")
	log.Println("Waiting for instruction...")
	time.Sleep(5 * time.Second)

	ticker := time.NewTicker(pollInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			rc.stopRecording()
			// Clear status on shutdown
			if err := rc.setAnnotation(ctx, statusAnnotation, string(StatusIdle)); err != nil {
				log.Printf("Warning: Failed to clear status on shutdown: %v", err)
			}
			return ctx.Err()
		case <-ticker.C:
			if err := rc.checkAnnotation(ctx, targetPID); err != nil {
				log.Printf("Error checking annotations: %v", err)
			}
		}
	}
}

func (rc *RecorderController) checkAnnotation(ctx context.Context, targetPID int) error {
	pod, err := rc.clientset.CoreV1().Pods(rc.config.Namespace).Get(
		ctx, rc.config.PodName, metav1.GetOptions{})
	if err != nil {
		return wrapErr("getting pod", err)
	}

	annotations := pod.GetAnnotations()
	if annotations == nil {
		return nil
	}

	if value, exists := annotations[liveRecordAnnotation]; exists {

		if value == "" {
            return nil
        }

		rc.recordingLock.Lock()
		defer rc.recordingLock.Unlock()

		switch value {
		case "start":
			if rc.recordingProcess == nil {
				if err := rc.startRecording(ctx, targetPID); err != nil {
					return wrapErr("starting recording", err)
				}
				log.Println("Recording started successfully")
			} else {
				log.Println("Recording already in progress, ignoring start command")
			}

		case "stop":
			if rc.recordingProcess != nil {
				rc.stopRecording()
				log.Println("Recording stopped successfully")
			} else {
				log.Println("No recording in progress, ignoring stop command")
			}

		default:
			log.Printf("Unknown value for %s annotation: %s", liveRecordAnnotation, value)
		}

		rc.clearAnnotation(ctx, liveRecordAnnotation)
	}

	return nil
}

func (rc *RecorderController) startRecording(ctx context.Context, targetPID int) error {
	// Set status to busy when recording starts
	if err := rc.setAnnotation(ctx, statusAnnotation, string(StatusBusy)); err != nil {
		log.Printf("Warning: Failed to set busy status: %v", err)
	}

	timestamp := time.Now().Format("20060102-150405")
	recordingFile := filepath.Join(
		recordingsDir,
		fmt.Sprintf("recording-%s.undo", timestamp),
	)

	if err := os.MkdirAll(recordingsDir, 0755); err != nil {
		return wrapErr("creating recordings directory", err)
	}

	cmd := exec.CommandContext(
		ctx,
		liveRecordPath,
		"-p", strconv.Itoa(targetPID),
		"--recording-file", recordingFile,
	)

	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	if err := cmd.Start(); err != nil {
		// Clear status if recording fails to start
		if statusErr := rc.clearAnnotation(ctx, statusAnnotation); statusErr != nil {
			log.Printf("Warning: Failed to clear status after recording start failure: %v", statusErr)
		}
		return wrapErr("starting live-record process", err)
	}

	rc.recordingProcess = cmd
	log.Printf("Recording started for PID %d to file %s", targetPID, recordingFile)

	go func() {
		log.Println("Monitoring live-record process...")
		if err := rc.recordingProcess.Wait(); err != nil {
			log.Printf("Live-record process exited with error: %v", err)
		} else {
			log.Println("Live-record process exited cleanly")
		}

		rc.recordingLock.Lock()
		defer rc.recordingLock.Unlock()
		rc.recordingProcess = nil
	}()

	return nil
}

func (rc *RecorderController) stopRecording() {
	if rc.recordingProcess == nil || rc.recordingProcess.Process == nil {
		return
	}

	log.Println("Stopping recording process (SIGINT)")

	if err := rc.recordingProcess.Process.Signal(syscall.SIGINT); err != nil {
		log.Printf("Error sending SIGINT to recording process: %v", err)
	}
}

func (rc *RecorderController) clearAnnotation(ctx context.Context, key string) error {
	patch := []byte(fmt.Sprintf(`{"metadata":{"annotations":{"%s":""}}}`, key))
	_, err := rc.clientset.CoreV1().Pods(rc.config.Namespace).Patch(
		ctx,
		rc.config.PodName,
		types.StrategicMergePatchType,
		patch,
		metav1.PatchOptions{},
	)
	if err != nil {
		log.Printf("Error clearing annotation %s: %v", key, err)
	}
	return err
}

func (rc *RecorderController) setAnnotation(ctx context.Context, key string, value string) error {
	patch := []byte(fmt.Sprintf(`{"metadata":{"annotations":{"%s":"%s"}}}`, key, value))
	_, err := rc.clientset.CoreV1().Pods(rc.config.Namespace).Patch(
		ctx,
		rc.config.PodName,
		types.StrategicMergePatchType,
		patch,
		metav1.PatchOptions{},
	)
	if err != nil {
		log.Printf("Error setting %s to %s: %v", key, value, err)
	}
	return err
}
