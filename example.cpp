/*
 * Example program demonstrating a race condition bug.
 *
 * This program computes weighted sums using shared weights that are
 * occasionally updated by another thread. The bug is that weights are
 * read without holding a consistent lock, allowing torn reads.
 *
 * For flow analysis:
 * - total = weighted_a + weighted_b (FORK: choose which to trace)
 * - weighted_a = value_a * weight_a
 * - weighted_b = value_b * weight_b
 */

#include <iostream>
#include <thread>
#include <mutex>
#include <atomic>
#include <cstdlib>
#include <cstring>

const int NUM_TASKS = 10000;

// Result of processing a task
struct Result {
    int task_id;
    int value_a;       // input value a
    int value_b;       // input value b
    int weight_a_used; // weight_a at time of computation
    int weight_b_used; // weight_b at time of computation
    int weighted_a;    // value_a * weight_a
    int weighted_b;    // value_b * weight_b
    int total;         // weighted_a + weighted_b
    int expected;      // what total should be with correct weights
};

// Fixed-size results array (avoids vector reallocation issues)
Result g_results[NUM_TASKS];
std::atomic<int> g_result_count{0};

// Shared weights - updated by a separate thread (the bug source)
int g_weight_a = 2;
int g_weight_b = 3;
std::mutex weight_mutex;

// Flag to stop weight updater
std::atomic<bool> g_stop_updater{false};

// Weight updater thread - occasionally changes weights temporarily
void weight_updater() {
    while (!g_stop_updater) {
        {
            std::lock_guard<std::mutex> lock(weight_mutex);
            g_weight_a = 10;
            g_weight_b = 10;
        }
        std::this_thread::yield();
        {
            std::lock_guard<std::mutex> lock(weight_mutex);
            g_weight_a = 2;
            g_weight_b = 3;
        }
        std::this_thread::yield();
    }
}

// Process a single task
// BUG: Reads weights without holding lock consistently - can see torn state
void process_task(int task_id, int value_a, int value_b) {
    Result result;
    result.task_id = task_id;
    result.value_a = value_a;
    result.value_b = value_b;

    // Read weight_a (might get old or new value)
    int wa;
    {
        std::lock_guard<std::mutex> lock(weight_mutex);
        wa = g_weight_a;
    }

    // Small gap where weights might change...
    std::this_thread::yield();

    // Read weight_b (might get different generation than weight_a!)
    int wb;
    {
        std::lock_guard<std::mutex> lock(weight_mutex);
        wb = g_weight_b;
    }

    result.weight_a_used = wa;
    result.weight_b_used = wb;

    // Compute weighted values - FORK POINT: total depends on BOTH
    result.weighted_a = value_a * wa;
    result.weighted_b = value_b * wb;
    result.total = result.weighted_a + result.weighted_b;

    // What we expected with consistent weights (2 and 3)
    result.expected = value_a * 2 + value_b * 3;

    // Store result
    int idx = g_result_count.fetch_add(1);
    g_results[idx] = result;
}

// Worker thread
void worker(int start, int count) {
    srand(42 + start);  // Deterministic but different per worker
    for (int i = 0; i < count; i++) {
        int task_id = start + i;
        int value_a = rand() % 100;
        int value_b = rand() % 100;
        process_task(task_id, value_a, value_b);
    }
}

int main() {
    std::cout << "Starting threaded work queue test...\n";
    std::cout << "Expected weights: a=" << 2 << ", b=" << 3 << "\n\n";

    // Start weight updater
    std::thread updater(weight_updater);

    // Start worker threads
    std::thread worker1(worker, 0, NUM_TASKS / 2);
    std::thread worker2(worker, NUM_TASKS / 2, NUM_TASKS / 2);

    // Wait for workers
    worker1.join();
    worker2.join();

    // Stop updater
    g_stop_updater = true;
    updater.join();

    // Check results for errors
    int error_count = 0;
    Result first_error;
    memset(&first_error, 0, sizeof(first_error));

    int total_results = g_result_count.load();
    for (int i = 0; i < total_results; i++) {
        const Result& r = g_results[i];
        if (r.total != r.expected) {
            if (error_count == 0) {
                first_error = r;
            }
            error_count++;
        }
    }

    std::cout << "Processed " << total_results << " tasks\n";
    std::cout << "Errors found: " << error_count << "\n";

    if (error_count > 0) {
        std::cout << "\nFirst error:\n";
        std::cout << "  Task ID: " << first_error.task_id << "\n";
        std::cout << "  value_a: " << first_error.value_a << "\n";
        std::cout << "  value_b: " << first_error.value_b << "\n";
        std::cout << "  weight_a_used: " << first_error.weight_a_used << "\n";
        std::cout << "  weight_b_used: " << first_error.weight_b_used << "\n";
        std::cout << "  weighted_a: " << first_error.weighted_a << "\n";
        std::cout << "  weighted_b: " << first_error.weighted_b << "\n";
        std::cout << "  total: " << first_error.total << "\n";
        std::cout << "  expected: " << first_error.expected << "\n";

        // Abort to create a point for debugging
        std::cerr << "ASSERTION FAILED: result mismatch!\n";
        abort();
    }

    std::cout << "All results correct!\n";
    return 0;
}
