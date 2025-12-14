#!/bin/bash

API_URL="http://localhost:8000/test_lab4"
echo "ТЕСТ 10 запросов"

for i in {1..10}; do 
    task = $i
    id = $((i/2))
    echo "task $task | id $id"
    curl -s -X POST "$API_URL" \
        -H "Content-Type: application/json" 
        -d "{\"id\": \"$id\", \"item\": \"$task\"}" 
done