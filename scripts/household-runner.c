#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <mach-o/dyld.h>
#include <limits.h>
#include <libgen.h>

#define SH_INTERPRETER "/bin/zsh"
#define PY_INTERPRETER "/usr/bin/python3"

void die(const char *msg) {
    fprintf(stderr, "Error: %s\n", msg);
    exit(EXIT_FAILURE);
}

int main(int argc, char *argv[]) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <script_name> [args...]\n", argv[0]);
        return EXIT_FAILURE;
    }

    char *script_name = argv[1];

    // 1. Path traversal prevention
    if (strchr(script_name, '/') != NULL || strstr(script_name, "..") != NULL) {
        die("Invalid script name. Path traversal detected.");
    }

    // 2. Resolve own directory
    char path[PATH_MAX];
    uint32_t size = sizeof(path);
    if (_NSGetExecutablePath(path, &size) != 0) {
        die("Failed to get executable path.");
    }

    char real_exe_path[PATH_MAX];
    if (realpath(path, real_exe_path) == NULL) {
        die("Failed to resolve real path of executable.");
    }

    char *scripts_dir = dirname(real_exe_path);
    size_t scripts_dir_len = strlen(scripts_dir);

    // 3. Build full script path
    char script_full_path[PATH_MAX];
    snprintf(script_full_path, sizeof(script_full_path), "%s/%s", scripts_dir, script_name);

    // 4. Resolve script path and verify it stays within scripts/
    char resolved_script_path[PATH_MAX];
    if (realpath(script_full_path, resolved_script_path) == NULL) {
        die("Script not found or cannot be resolved.");
    }

    if (strncmp(resolved_script_path, scripts_dir, scripts_dir_len) != 0) {
        die("Security violation: Script resolved outside of authorized directory.");
    }

    // 5. Select interpreter
    const char *interpreter = NULL;
    char *ext = strrchr(script_name, '.');
    if (ext != NULL) {
        if (strcmp(ext, ".sh") == 0) {
            interpreter = SH_INTERPRETER;
        } else if (strcmp(ext, ".py") == 0) {
            interpreter = PY_INTERPRETER;
        }
    }

    if (interpreter == NULL) {
        die("Unsupported script extension. Use .sh or .py.");
    }

    // 6. Prepare arguments for execv
    // [interpreter, script_path, arg1, arg2, ..., NULL]
    char **exec_args = malloc(sizeof(char *) * (argc + 1));
    if (exec_args == NULL) die("Memory allocation failure.");

    exec_args[0] = (char *)interpreter;
    exec_args[1] = resolved_script_path;
    for (int i = 2; i < argc; i++) {
        exec_args[i] = argv[i];
    }
    exec_args[argc] = NULL;

    // 7. Execute
    execv(interpreter, exec_args);

    // If execv returns, it failed
    perror("execv");
    return EXIT_FAILURE;
}
