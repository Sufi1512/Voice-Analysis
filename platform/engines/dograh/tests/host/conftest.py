def pytest_configure(config):
    config.addinivalue_line("markers", "network: clones the real pinned engines (needs GitHub access)")
