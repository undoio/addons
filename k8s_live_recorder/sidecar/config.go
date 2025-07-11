// config.go defines the configuration structure and loading logic for the application.
package main

import (
	"os"
)

type Config struct {
	// Kubernetes related
	Namespace string
	PodName   string

	// Target process related
	AppProcessName string

	// AWS S3 related
	AWSAccessKeyID     string
	AWSSecretAccessKey string
	S3BucketName       string
	S3Region           string
	S3KeyPrefix        string
}

// Environment variables
const (
	namespaceEnv       = "POD_NAMESPACE"
	podNameEnv         = "POD_NAME"
	appProcessNameEnv  = "APP_PROCESS_NAME"
	awsAccessKeyIDEnv  = "AWS_ACCESS_KEY_ID"
	awsSecretAccessEnv = "AWS_SECRET_ACCESS_KEY"
	s3BucketNameEnv    = "S3_BUCKET_NAME"
	s3RegionEnv        = "S3_REGION"
	s3KeyPrefixEnv     = "S3_KEY_PREFIX"
)

// Defaults
const (
	defaultNamespace   = "default"
	defaultS3Region    = "us-east-1"
	defaultS3KeyPrefix = "recordings"
)

func loadConfig() (*Config, error) {
	cfg := &Config{
		Namespace:          getEnvOrDefault(namespaceEnv, defaultNamespace),
		PodName:            os.Getenv(podNameEnv),
		AppProcessName:     os.Getenv(appProcessNameEnv),
		AWSAccessKeyID:     os.Getenv(awsAccessKeyIDEnv),
		AWSSecretAccessKey: os.Getenv(awsSecretAccessEnv),
		S3BucketName:       os.Getenv(s3BucketNameEnv),
		S3Region:           getEnvOrDefault(s3RegionEnv, defaultS3Region),
		S3KeyPrefix:        getEnvOrDefault(s3KeyPrefixEnv, defaultS3KeyPrefix),
	}

	if cfg.PodName == "" {
		return nil, wrapErr("validating configuration",
			&MissingEnvError{EnvVar: podNameEnv})
	}

	// AWS S3 credentials are now required for the app to start
	if cfg.S3BucketName == "" {
		return nil, wrapErr("validating S3 configuration",
			&MissingEnvError{EnvVar: s3BucketNameEnv})
	}

	if cfg.AWSAccessKeyID == "" {
		return nil, wrapErr("validating AWS credentials",
			&MissingEnvError{EnvVar: awsAccessKeyIDEnv})
	}

	if cfg.AWSSecretAccessKey == "" {
		return nil, wrapErr("validating AWS credentials",
			&MissingEnvError{EnvVar: awsSecretAccessEnv})
	}

	return cfg, nil
}

func getEnvOrDefault(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

type MissingEnvError struct {
	EnvVar string
}

func (e *MissingEnvError) Error() string {
	return "missing required environment variable: " + e.EnvVar
}
