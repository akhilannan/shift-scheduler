### Fixed

- **Critical Bug:** Resolved a fatal `ImportError` that caused the packaged Windows executable (`.exe`) to crash immediately on launch.
- **Root Cause:** The error was due to missing binary files (`DLLs`) from the `ortools` (CP-SAT solver) dependency that were not being included by PyInstaller during the build process.
- **Solution:** The build script in the GitHub Actions workflow has been updated to explicitly collect and bundle all necessary `ortools` binaries, ensuring the executable is self-contained and runs correctly.