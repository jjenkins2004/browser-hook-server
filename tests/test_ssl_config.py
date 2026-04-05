import os
import unittest
from unittest.mock import patch

import certifi

from app.ssl_config import configure_ca_bundle


class ConfigureCABundleTests(unittest.TestCase):
    def test_sets_tls_bundle_env_vars_to_certifi(self) -> None:
        expected_bundle = certifi.where()

        with patch.dict(os.environ, {}, clear=True):
            result = configure_ca_bundle()

            self.assertEqual(result, expected_bundle)
            self.assertEqual(os.environ["SSL_CERT_FILE"], expected_bundle)
            self.assertEqual(os.environ["REQUESTS_CA_BUNDLE"], expected_bundle)
            self.assertEqual(os.environ["CURL_CA_BUNDLE"], expected_bundle)


if __name__ == "__main__":
    unittest.main()
