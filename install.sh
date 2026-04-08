#!/bin/bash
set -e

echo "============================================"
echo "  RepairXpert IndAutomation — Plant Install"
echo "  Enterprise Edition"
echo "============================================"
echo ""

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker is not installed."
    echo "Install Docker Desktop: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check Docker Compose
if ! docker compose version &> /dev/null; then
    echo "ERROR: Docker Compose is not available."
    echo "Docker Desktop includes Compose. Update Docker Desktop."
    exit 1
fi

echo "Building and starting RepairXpert..."
docker compose up -d --build

echo ""
echo "============================================"
echo "  RepairXpert is running!"
echo "  Open: http://localhost:8300"
echo ""
echo "  View logs:    docker compose logs -f"
echo "  Stop:         docker compose down"
echo "  Restart:      docker compose restart"
echo "============================================"
