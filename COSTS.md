# COSTS — расходы и время

**Статус:** измеренных прогонов нет. Пустая история не означает нулевую стоимость.

Для каждого платного вызова: сначала preflight, затем log с уникальным ID. Если провайдер вернул фактическую стоимость, передавайте --actual-usd; иначе запись будет помечена estimate=true.

    python hooks/cost_log.py preflight --project megafon-demo --model deepseek-chat --tin 20000 --tout 5000
    python hooks/cost_log.py log --project megafon-demo --run demo-1 --step 3 --model deepseek-chat --tin 20000 --tout 5000 --sec 18 --id unique-call-id --estimate
    python hooks/cost_log.py report --project megafon-demo

Команда report перегенерирует этот файл с суммой по прогонам, временем, стоимостью и детализацией вызовов. Поиск, число открытых страниц, внешние инструменты и ручная доработка фиксируются отдельно в таблице «Внешние расходы и ручное время»; они не входят в LLM subtotal автоматически.

Тарифы в конфигурации — ориентир и должны сверяться с актуальным прайс-листом. Неизвестная цена блокирует preflight.