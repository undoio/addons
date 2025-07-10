// finder.go defines functions to locate and copy the executable of a target process
package main

import (
	"bufio"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

func findTargetProcess(targetProcessName string) (int, error) {
	currentPID := os.Getpid()

	entries, err := os.ReadDir("/proc")
	if err != nil {
		return 0, wrapErr("reading /proc directory", err)
	}

	for _, entry := range entries {

		if !entry.IsDir() || !isDigit(entry.Name()) {
			continue
		}

		pid, err := strconv.Atoi(entry.Name())
		if err != nil {
			continue
		}

		if pid == currentPID {
			continue
		}

		exePath, err := os.Readlink(filepath.Join("/proc", entry.Name(), "exe"))
		if err != nil {
			continue // skip if we can't read exe
		}

		if filepath.Base(exePath) == targetProcessName {
			return pid, nil
		}
	}

	logAvailableProcesses()

	return 0, wrapErr("finding target process", fmt.Errorf("process %q not found", targetProcessName))
}

func copyTargetExecutable(targetPID int) error {
	exePath := filepath.Join("/proc", strconv.Itoa(targetPID), "exe")
	dstPath, err := os.Readlink(filepath.Join("/proc", strconv.Itoa(targetPID), "exe"))
	if err != nil {
		return wrapErr("reading executable path", err)
	}

	if err := os.MkdirAll(filepath.Dir(dstPath), 0755); err != nil {
		return wrapErr("creating directory structure", err)
	}

	srcFile, err := os.Open(exePath)
	if err != nil {
		return wrapErr("opening source executable", err)
	}
	defer srcFile.Close()

	dstFile, err := os.OpenFile(dstPath, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0755)
	if err != nil {
		return wrapErr("creating destination file", err)
	}
	defer dstFile.Close()

	if _, err := io.Copy(dstFile, srcFile); err != nil {
		return wrapErr("copying executable content", err)
	}

	return nil
}

type SharedLibrary struct {
	Path     string 
	RealPath string 
}

func copySharedLibraries(targetPID int) error {
	libs, err := getSharedLibraries(targetPID)
	if err != nil {
		return wrapErr("getting shared libraries", err)
	}

	fmt.Printf("Found %d shared libraries to copy\n", len(libs))

	for _, lib := range libs {
		if err := copySharedLibrary(lib); err != nil {
			fmt.Printf("Warning: failed to copy library %s: %v\n", lib.Path, err)
			// Continue with other libraries instead of failing completely
		} else {
			fmt.Printf("Successfully copied library: %s\n", lib.Path)
		}
	}

	return nil
}

func getSharedLibraries(targetPID int) ([]SharedLibrary, error) {
	mapsPath := filepath.Join("/proc", strconv.Itoa(targetPID), "maps")
	file, err := os.Open(mapsPath)
	if err != nil {
		return nil, wrapErr("opening maps file", err)
	}
	defer file.Close()

	libMap := make(map[string]SharedLibrary)
	scanner := bufio.NewScanner(file)

	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}

		// Parse maps line format: address perms offset dev inode pathname
		fields := strings.Fields(line)
		if len(fields) < 6 {
			continue
		}

		pathname := fields[5]
		
		if !isSharedLibrary(pathname) {
			continue
		}

		if _, exists := libMap[pathname]; exists {
			continue
		}

		realPath, err := resolveLibraryPath(targetPID, pathname)
		if err != nil {
			fmt.Printf("Warning: could not resolve path for %s: %v\n", pathname, err)
			continue
		}

		libMap[pathname] = SharedLibrary{
			Path:     pathname,
			RealPath: realPath,
		}
	}

	if err := scanner.Err(); err != nil {
		return nil, wrapErr("scanning maps file", err)
	}

	libs := make([]SharedLibrary, 0, len(libMap))
	for _, lib := range libMap {
		libs = append(libs, lib)
	}

	return libs, nil
}

func isSharedLibrary(pathname string) bool {

	if strings.HasPrefix(pathname, "[") || pathname == "" {
		return false
	}

	if strings.HasSuffix(pathname, " (deleted)") {
		return false
	}

	return strings.Contains(pathname, ".so") ||
		strings.HasPrefix(pathname, "/lib/") ||
		strings.HasPrefix(pathname, "/lib64/") ||
		strings.HasPrefix(pathname, "/usr/lib/") ||
		strings.HasPrefix(pathname, "/usr/lib64/") ||
		strings.HasPrefix(pathname, "/usr/local/lib/")
}

func resolveLibraryPath(targetPID int, libPath string) (string, error) {

	procRootPath := filepath.Join("/proc", strconv.Itoa(targetPID), "root", libPath)
	
	if _, err := os.Stat(procRootPath); err != nil {
		return "", wrapErr("checking library file", err)
	}

	return procRootPath, nil
}

func copySharedLibrary(lib SharedLibrary) error {

	destDir := filepath.Dir(lib.Path)
	if err := os.MkdirAll(destDir, 0755); err != nil {
		return wrapErr("creating library directory", err)
	}

	srcFile, err := os.Open(lib.RealPath)
	if err != nil {
		return wrapErr("opening source library", err)
	}
	defer srcFile.Close()

	dstFile, err := os.OpenFile(lib.Path, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0755)
	if err != nil {
		return wrapErr("creating destination library", err)
	}
	defer dstFile.Close()

	if _, err := io.Copy(dstFile, srcFile); err != nil {
		return wrapErr("copying library content", err)
	}

	return nil
}

func isDigit(s string) bool {
	for _, r := range s {
		if r < '0' || r > '9' {
			return false
		}
	}
	return true
}

func logAvailableProcesses() {
	entries, err := os.ReadDir("/proc")
	if err != nil {
		return
	}

	for _, entry := range entries {
		if entry.IsDir() && isDigit(entry.Name()) {
			exePath, err := os.Readlink(filepath.Join("/proc", entry.Name(), "exe"))
			if err == nil {
				cmdline, _ := os.ReadFile(filepath.Join("/proc", entry.Name(), "cmdline"))
				cmdlineStr := strings.ReplaceAll(string(cmdline), "\x00", " ")
				fmt.Printf("PID %s → %s (%s)\n", entry.Name(), exePath, cmdlineStr)
			}
		}
	}
}
