#!/bin/bash
set -e

# Patch config.yaml with LM_STUDIO_URL if set
if [ -n "$LM_STUDIO_URL" ]; then
    # Replace the base_url line in config.yaml
    sed -i "s|base_url:.*|base_url: ${LM_STUDIO_URL}/v1|" /app/config.yaml
    echo "[entrypoint] LM Studio URL set to: ${LM_STUDIO_URL}/v1"
fi

exec "$@"
