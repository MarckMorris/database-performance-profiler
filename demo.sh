#!/bin/bash
echo "Starting Database Performance Profiler..."
docker-compose up -d
sleep 10
pip install psycopg2-binary
python src/profiler.py
