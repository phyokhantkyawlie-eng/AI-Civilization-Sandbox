"""Archived entry point: network smoke tests are disabled in this offline build."""


def run_smoke(settings=None):
    print("External API smoke tests are disabled. Use python -m civsandbox --headless instead.")
    return 2


if __name__ == "__main__":
    raise SystemExit(run_smoke())
