/**
 * Allows the LiveRecorder API to follow fork() and record
 * all children processes.
 *
 * See README.md for how to compile and use.
 *
 */
#define _POSIX_SOURCE
#define _GNU_SOURCE

#include "undolr.h"
#include "undolr_deprecated.h"

#include <errno.h>
#include <stdio.h>
#include <sys/types.h>
#include <unistd.h>
#include <string.h>
#include <stdbool.h>
#include <time.h>
#include <stdlib.h>
#include <dlfcn.h>
#include <linux/limits.h>

extern char *__progname;

/**
 * \brief Checks if the process needs to be recorded.
 *
 * \return True if the process needs recording, False otherwise.
 */
static bool
process_needs_recording(void)
{
    if (strncmp(__progname, "undo", 4) == 0)
    {
        if (unsetenv("LD_PRELOAD"))
        {
            perror("unsetenv");
            exit(1);
        }
        return false;
    }
    return true;
}

/**
 * \brief Wraps dlsym and handles errors internally.
 *
 * \param  sym The symbol name to look for.
 *
 * \return A pointer to the symbol if found, NULL otherwise.
 */
static void *
get_sym_addr(const char *sym)
{
    void *fptr = NULL;

    fptr = dlsym(RTLD_NEXT, sym);
    if (fptr == NULL)
    {
        fprintf(stderr, "Error: %s, calling dlsym with %s\n",
                        dlerror(), sym);
        abort();
    }
    return fptr;
}

/**
 * \brief Calls the UNDO API to start recording the process.
 *
 */
static void
start_recording()
{
    undolr_error_t err;
    int e = undolr_start(&err);
    if (e)
    {
        perror("undolr_start")
        fprintf(stderr, "%s\n", undolr_error_string(errno));
        return;
    }

    time_t cur_time = time(0);
    char rec_fname[PATH_MAX] = {0};

    // Recording files are saved in /tmp, change this if you want them saved somewhere else.
    e = snprintf(rec_fname, PATH_MAX, "/tmp/%s_%d_%lu.undo", __progname, getpid(), cur_time);
    if (e < 0)
    {
        fprintf(stderr, "failed creating path to the recording, snprintf() returned %d\n", e);
        return;
    }

    e = undolr_save_on_termination(rec_fname);
    if (e)
    {
        perror("undolr_save_on_termination")
        fprintf(stderr, "%s\n", undolr_error_string(errno));
        return;
    }
    return;
}

/**
 * /brief Interpose fork to record forked processes.
 *
 * /return  The pid of newly created process.
 */
pid_t
fork(void)
{
    typedef pid_t (*fork_function)();
    static fork_function real_fork = NULL;

    if (!real_fork)
    {
        real_fork = (fork_function)get_sym_addr("fork");
    }

    pid_t pid = real_fork();
    if (pid == 0)
    {
        if (process_needs_recording())
        {
            // Start recording the child
            start_recording();
        }
    }
    return pid;
}

/**
 * This function gets called before main() (see gcc's constructor attribute for details)
 *
 * The intended use is for it to record the parent process.
 *
 */
static void attach_lr(int, char**, char**) __attribute__ ((constructor));

static void
attach_lr(int argc, char **argv, char **envp)
{
    /* Do not follow Undo processes */
    if (!process_needs_recording())
    {
        return;
    }

    start_recording();
}
