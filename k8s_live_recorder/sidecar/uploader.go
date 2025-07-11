// uploader.go defines the logic for uploading recording files to S3.
package main

import (
	"context"
	"log"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/aws/session"
	"github.com/aws/aws-sdk-go/service/s3/s3manager"
)

func (rc *RecorderController) startUploaderLoop(ctx context.Context, started chan struct{}) {
	ticker := time.NewTicker(10 * time.Second)

	log.Println("Starting S3 uploader loop...")
	go func() {
		close(started)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				log.Println("Uploader loop shutting down")
				return
			case <-ticker.C:
				rc.checkAndUploadRecordings(ctx)
			}
		}
	}()
}

func (rc *RecorderController) checkAndUploadRecordings(ctx context.Context) {
	files, err := rc.findRecordingFiles()
	if err != nil {
		log.Printf("Error finding recording files: %v", err)
		return
	}

	if len(files) == 0 {
		return
	}

	log.Printf("Found %d recording file(s) to upload", len(files))

	successfulUploads := 0
	for _, file := range files {
		if err := rc.uploadFileToS3(file); err != nil {
			log.Printf("Error uploading file %s: %v", file, err)
			continue
		}
		successfulUploads++
	}

	if successfulUploads == len(files) {
		if err := rc.clearAnnotation(ctx, statusAnnotation); err != nil {
			log.Printf("Warning: Failed to clear status after successful uploads: %v", err)
		}
		log.Println("All recordings uploaded successfully, status cleared")
	} else if successfulUploads > 0 {
		log.Printf("Partial upload success: %d/%d files uploaded, keeping busy status", successfulUploads, len(files))
	}
}

func (rc *RecorderController) findRecordingFiles() ([]string, error) {
	entries, err := os.ReadDir(recordingsDir)
	if err != nil {
		return nil, wrapErr("reading recordings directory", err)
	}

	var files []string
	for _, entry := range entries {
		if !entry.IsDir() && strings.HasSuffix(entry.Name(), ".undo") {
			files = append(files, filepath.Join(recordingsDir, entry.Name()))
		}
	}

	return files, nil
}

func (rc *RecorderController) uploadFileToS3(filePath string) error {
	file, err := os.Open(filePath)
	if err != nil {
		return wrapErr("opening file for upload", err)
	}
	defer file.Close()

	fileName := filepath.Base(filePath)
	s3Key := filepath.Join(rc.config.S3KeyPrefix, fileName)

	sess, err := session.NewSession(&aws.Config{
		Region: aws.String(rc.config.S3Region),
	})
	if err != nil {
		return wrapErr("creating AWS session", err)
	}

	uploader := s3manager.NewUploader(sess)
	result, err := uploader.Upload(&s3manager.UploadInput{
		Bucket: aws.String(rc.config.S3BucketName),
		Key:    aws.String(s3Key),
		Body:   file,
	})
	if err != nil {
		return wrapErr("uploading file to S3", err)
	}

	log.Printf("Successfully uploaded file to %s", result.Location)

	if err := os.Remove(filePath); err != nil {
		log.Printf("Warning: Failed to delete local file %s: %v", filePath, err)
	} else {
		log.Printf("Deleted local file %s", filePath)
	}

	return nil
}
