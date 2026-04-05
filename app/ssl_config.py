import logging
import os
import ssl

import certifi

logger = logging.getLogger(__name__)


def configure_ca_bundle() -> str:
    """Point Python TLS clients at a known CA bundle for cloud websocket calls."""
    ca_bundle = certifi.where()

    for env_var in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        current_value = os.environ.get(env_var)
        if current_value != ca_bundle:
            os.environ[env_var] = ca_bundle

    logger.debug("Configured CA bundle for outbound TLS connections: %s", ca_bundle)
    return ca_bundle


def build_ssl_context() -> ssl.SSLContext:
    """Build an SSL context pinned to certifi's CA bundle."""
    ca_bundle = configure_ca_bundle()
    return ssl.create_default_context(cafile=ca_bundle)
