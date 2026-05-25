# Tasks & Lessons Learned

## 1. PyPI Package Version Constraint Errors
*   **Mistake:** Assumed that the newly reverse-engineered Ulanzi D200 controller library `strmdck` had a stable release version `1.0.0` or higher, pinning `strmdck>=1.0.0` in `requirements.txt`. Additionally, when unpinning to just `strmdck`, standard `pip` still failed because by default it filters out and ignores pre-release/release candidate packages (like `0.1.0rc1`) unless explicitly requested.
*   **Consequence:** `pip install` failed with `No matching distribution found` in both instances.
*   **Rule for the Future:** 
    > [!IMPORTANT]
    > **Dependency Verification Rule:** Before adding any third-party library to a dependencies file (e.g., `requirements.txt`, `setup.py`, `package.json`), always perform a search on the package manager repository (e.g., PyPI, npm) to verify the exact latest available versions. If the package only has pre-releases (e.g., `0.1.0rc1`), you must specify the **exact pre-release version** (e.g., `strmdck==0.1.0rc1`) or use the `--pre` flag to bypass pip's default pre-release filtering behavior.

## 2. Environment Discrepancy & Decoupled Imports
*   **Mistake:** Did not check the user's host system Python version. The user is running Python 3.8.10, whereas the Ulanzi D200 library `strmdck` strictly requires Python >= 3.9. This caused PyPI to completely hide the package wheel from the user's environment.
*   **Consequence:** `pip install` returned `versions: none` for `strmdck==0.1.0rc1` on Python 3.8.
*   **Design Solution:** The codebase is designed with a **decoupled imports pattern** (gracefully catching `ImportError` inside `deck_manager.py`). This allows the entire simulator and logic to run perfectly on Python 3.8 without `strmdck` installed.
*   **Rule for the Future:**
    > [!TIP]
    > **Mock/Simulator Independence:** Always decouple third-party hardware or platform-specific libraries inside a `try/except ImportError` block so that developer-focused simulators and validation suites can run out-of-the-box on constrained environments (like older Python versions) without failing.

## 3. Dynamic Hardware Naming & Telemetry Searches
*   **Mistake:** Assumed that querying LibreHardwareMonitor's JSON API tree with simple keywords like `"cpu"` or `"gpu"` would match the hardware node names. However, LHM publishes the actual hardware vendor strings (e.g., `"Intel Core i9-13900K"` or `"NVIDIA GeForce RTX 4090"`), which do not contain generic words like `"cpu"` or `"gpu"`.
*   **Consequence:** The recursive path-based parser returned `None` during unit testing because it failed to resolve nodes on the first hierarchical level.
*   **Rule for the Future:**
    > [!IMPORTANT]
    > **Robust Telemetry Keyword Fallbacks:** When querying hardware monitoring or WMI nodes using path-based queries, always define a robust list of vendor-specific fallback keywords (e.g., `"intel"`, `"amd"`, `"nvidia"`, `"geforce"`, `"ryzen"`, `"radeon"`, `"core"`) to ensure that dynamic hardware vendor names resolve correctly across any developer or client environment. Always test these trees using realistic mock structures containing regional formatting differences (like decimal commas in `"50,2 °C"`).
