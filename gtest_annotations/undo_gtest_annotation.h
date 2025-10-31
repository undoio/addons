#ifndef UNDO_GTEST_ANNOTATION_H_
#define UNDO_GTEST_ANNOTATION_H_

#include <stdio.h>
#include <undoex-test-annotations.h>

#include <mutex>
#include <thread>
#include <unordered_map>

namespace undo_annotation
{

class UndoAnnotationListener : public ::testing::EmptyTestEventListener
{
private:
    /** Per-thread instances of the annotation state */
    std::unordered_map<std::thread::id, undoex_test_annotation_t *> m_thread_state;
    /** A lock protecting access to m_thread_state */
    std::mutex m_thread_state_lock;

public:
    virtual void OnTestStart(const testing::TestInfo &testInfo)
    {
        // Create an instance of an annotation context, and associate it
        // with this thread.
        std::string full_name = std::string(testInfo.test_suite_name()) + "." + testInfo.name();
        undoex_test_annotation_t *annotation = undoex_test_annotation_new(full_name.c_str(), true);
        undoex_test_annotation_start(annotation);

        const std::thread::id thread_id = std::this_thread::get_id();

        std::lock_guard<std::mutex> lock(m_thread_state_lock);
        if (m_thread_state.count(thread_id))
        {
            // We don't expect there to be an existing entry here.
            // Handle it silently out of politeness.
            auto old = m_thread_state[thread_id];
            if (old)
            {
                undoex_test_annotation_free(old);
            }
        }
        m_thread_state[thread_id] = annotation;
    }

    virtual void OnTestEnd(const testing::TestInfo &testInfo)
    {
        const std::thread::id thread_id = std::this_thread::get_id();
        undoex_test_annotation_t *annotation;

        {
            std::lock_guard<std::mutex> lock(m_thread_state_lock);
            if (!m_thread_state.count(thread_id))
            {
                // We don't expect this to happen, but swallow
                // the error silently out of politeness.
                return;
            }
            annotation = m_thread_state.at(thread_id);
            m_thread_state.erase(thread_id);
        }

        undoex_test_result_t test_result = undoex_test_result_UNKNOWN;

        if (testInfo.result()->Failed())
        {
            test_result = undoex_test_result_FAILURE;
        }
        else if (testInfo.result()->Skipped())
        {
            test_result = undoex_test_result_SKIPPED;
        }
        else if (testInfo.result()->Passed())
        {
            test_result = undoex_test_result_SUCCESS;
        }

        undoex_test_annotation_end(annotation);
        undoex_test_annotation_set_result(annotation, test_result);
        undoex_test_annotation_free(annotation);
    }
};

} // namespace undo_annotation

#endif
