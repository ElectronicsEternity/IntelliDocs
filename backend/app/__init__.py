"""IntelliDocs backend application package."""

import truststore


# Use the operating system's managed CA store for outbound HTTPS. This is
# especially important on managed Windows machines whose trusted enterprise
# certificates are not part of certifi's static bundle.
truststore.inject_into_ssl()
