#!/bin/bash

# Fast restart script for the bot
echo "🔄 Fast restarting bot..."

# Stop containers
docker-compose down

# Build with cache (much faster than --no-cache)
docker-compose build

# Start containers
docker-compose up -d

echo "✅ Bot restarted successfully!"
echo "📊 View logs: docker-compose logs -f" 