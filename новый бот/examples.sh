#!/bin/bash
# Примеры использования REST API через curl

API_URL="http://localhost:8000"

echo "========================================"
echo "Yandex Phone Checker - Примеры curl"
echo "========================================"
echo ""

# Пример 1: Информация о сервере
echo "1. Информация о сервере:"
echo "curl $API_URL/"
echo ""
curl -s "$API_URL/" | jq .
echo ""
echo ""

# Пример 2: Проверка здоровья
echo "2. Проверка здоровья:"
echo "curl $API_URL/health"
echo ""
curl -s "$API_URL/health" | jq .
echo ""
echo ""

# Пример 3: Проверить один номер (синхронно)
echo "3. Проверить один номер (синхронно):"
echo "curl -X POST $API_URL/api/check/phone \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -d '{\"phone\": \"89212810954\"}'"
echo ""
curl -s -X POST "$API_URL/api/check/phone" \
  -H "Content-Type: application/json" \
  -d '{"phone": "89212810954"}' | jq .
echo ""
echo ""

# Пример 4: Проверить несколько номеров (асинхронно)
echo "4. Запустить проверку нескольких номеров:"
echo "curl -X POST $API_URL/api/check/batch \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -d '{\"phones\": [\"89212810954\", \"89213456789\"]}'"
echo ""

TASK_RESPONSE=$(curl -s -X POST "$API_URL/api/check/batch" \
  -H "Content-Type: application/json" \
  -d '{"phones": ["89212810954", "89213456789", "89999999999"]}')

echo "$TASK_RESPONSE" | jq .
TASK_ID=$(echo "$TASK_RESPONSE" | jq -r '.task_id')

echo ""
echo "Task ID: $TASK_ID"
echo ""
echo ""

# Пример 5: Проверить статус задачи
echo "5. Проверить статус задачи (в течение 30 сек):"
echo "curl $API_URL/api/status/$TASK_ID"
echo ""

for i in {1..30}; do
    STATUS=$(curl -s "$API_URL/api/status/$TASK_ID" | jq -r '.status')
    PERCENT=$(curl -s "$API_URL/api/status/$TASK_ID" | jq -r '.percent')
    PROCESSED=$(curl -s "$API_URL/api/status/$TASK_ID" | jq -r '.processed')
    TOTAL=$(curl -s "$API_URL/api/status/$TASK_ID" | jq -r '.total')

    printf "\rПопытка $i: Status=$STATUS, Progress=$PROCESSED/$TOTAL ($PERCENT%)"

    if [ "$STATUS" != "processing" ]; then
        echo ""
        break
    fi

    sleep 1
done

echo ""
echo ""

# Пример 6: Получить полные результаты
echo "6. Получить полные результаты:"
echo "curl $API_URL/api/results/$TASK_ID"
echo ""
curl -s "$API_URL/api/results/$TASK_ID" | jq .
echo ""
echo ""

# Пример 7: Получить статистику
echo "7. Получить статистику:"
echo "curl $API_URL/api/stats"
echo ""
curl -s "$API_URL/api/stats" | jq .
echo ""
echo ""

echo "========================================"
echo "Примеры завершены!"
echo "========================================"
