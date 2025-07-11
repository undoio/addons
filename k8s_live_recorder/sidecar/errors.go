// errors.go defines utility functions for error handling in the application.
package main

import (
	"fmt"
)

// wrapErr creates a new error that wraps the original error with additional context.
// It uses the %w verb for error chaining as recommended in Effective Go.
func wrapErr(op string, err error) error {
	if err == nil {
		return nil
	}
	return fmt.Errorf("%s: %w", op, err)
}
