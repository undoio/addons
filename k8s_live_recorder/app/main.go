package main

import (
    "database/sql"
    "fmt"
    "net/http"
    "time"
    
    _ "github.com/mattn/go-sqlite3" // SQLite driver (uses CGO and shared libraries)
)

var db *sql.DB

func initDB() error {
    var err error
    db, err = sql.Open("sqlite3", ":memory:")
    if err != nil {
        return err
    }
    
    // Create a simple table
    _, err = db.Exec(`CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )`)
    if err != nil {
        return err
    }
    
    // Insert a sample message
    _, err = db.Exec("INSERT INTO messages (message) VALUES (?)", "Hello from SQLite!")
    return err
}

func rootHandler(w http.ResponseWriter, r *http.Request) {
    // Query the database
    var message string
    var createdAt string
    err := db.QueryRow("SELECT message, created_at FROM messages ORDER BY id DESC LIMIT 1").Scan(&message, &createdAt)
    if err != nil {
        fmt.Fprintf(w, "Hello, World! (Database error: %v)", err)
        return
    }
    
    fmt.Fprintf(w, "Hello, World!\nLatest message from SQLite: %s (created: %s)\n", message, createdAt)
}

func dbHandler(w http.ResponseWriter, r *http.Request) {
    rows, err := db.Query("SELECT id, message, created_at FROM messages ORDER BY id DESC")
    if err != nil {
        http.Error(w, err.Error(), http.StatusInternalServerError)
        return
    }
    defer rows.Close()
    
    fmt.Fprintf(w, "Messages from SQLite database:\n\n")
    for rows.Next() {
        var id int
        var message, createdAt string
        if err := rows.Scan(&id, &message, &createdAt); err != nil {
            http.Error(w, err.Error(), http.StatusInternalServerError)
            return
        }
        fmt.Fprintf(w, "ID: %d, Message: %s, Created: %s\n", id, message, createdAt)
    }
}

func crashHandler(w http.ResponseWriter, r *http.Request) {
    fmt.Println("Time to crash! Triggering SIGSEGV...")
    
    go func() {
        time.Sleep(2 * time.Second)
        fmt.Println("Crashing with SIGSEGV")
        // SIGSEGV: dereference nil pointer
        var p *int
        *p = 1 // This will cause a segmentation fault
    }()
    
    fmt.Fprintf(w, "This will crash!")
}

func main() {
    // Initialize the SQLite database
    if err := initDB(); err != nil {
        fmt.Printf("Failed to initialize database: %v\n", err)
        return
    }
    defer db.Close()
    
    http.HandleFunc("/", rootHandler)
    http.HandleFunc("/crash", crashHandler)
    http.HandleFunc("/db", dbHandler)
    
    fmt.Println("Server listening on :8080")
    fmt.Println("Routes available:")
    fmt.Println("  / - Hello World with SQLite message")
    fmt.Println("  /crash - Trigger crash")
    fmt.Println("  /db - Show all database messages")
    http.ListenAndServe(":8080", nil)
}