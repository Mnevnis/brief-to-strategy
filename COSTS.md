# COSTS — расходы и время

**Статус:** измеренных прогонов нет. Пустая история не означает нулевую стоимость.

После каждого платного вызова сначала проверьте бюджет, затем зарегистрируйте usage:

    python hooks/cost_log.py preflight --project megafon-demo --model deepseek-chat --tin 20000 --tout 5000
    python hooks/cost_log.py log --project megafon-demo --run demo-1 --step 3 --model deepseek-chat --tin 20000 --tout 5000 --sec 18 --id unique-call-id --estimate
    python hooks/cost_log.py report --project megafon-demo

Тарифы в конфигурации — ориентир и должны сверяться с актуальным прайс-листом. Поиск, инструменты и ручная доработка учитываются отдельно. Неизвестная цена блокирует preflight.
