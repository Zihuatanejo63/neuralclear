"""Test package for NeuralClear.

Sandbox tests set placeholder variable names in the process environment.
These are not production secrets and are refused if production mode is on.
"""

import os

os.environ.setdefault("NEURALCLEAR_MODE", "sandbox")
os.environ.setdefault("NEURALCLEAR_API_KEY", "test-api-key")
os.environ.setdefault("NEURALCLEAR_READ_API_KEY", "test-read-key")
os.environ.setdefault("NEURALCLEAR_SIGNING_SECRET", "test-signing-secret")
os.environ.setdefault("NEURALCLEAR_SIGNING_KEY_ID", "test-receipt")

TEST_API_KEY = "test-api-key"
TEST_READ_KEY = "test-read-key"
