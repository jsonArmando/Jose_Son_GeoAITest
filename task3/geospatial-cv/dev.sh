#!/bin/bash

case "$1" in
    "start")
        echo "🚀 Starting services..."
        docker-compose up -d
        ;;
    "restart")
        echo "🔄 Restarting application..."
        docker-compose restart geospatial-api
        ;;
    "rebuild")
        echo "🛠️ Rebuilding application..."
        docker-compose build geospatial-api
        docker-compose up -d
        ;;
    "logs")
        echo "📋 Showing logs..."
        docker-compose logs -f geospatial-api
        ;;
    "stop")
        echo "⏹️ Stopping services..."
        docker-compose down
        ;;
    "clean")
        echo "🧹 Cleaning everything..."
        docker-compose down -v
        docker system prune -f
        ;;
    *)
        echo "Usage: ./dev.sh {start|restart|rebuild|logs|stop|clean}"
        ;;
esac