# Executive handoff — fictional-operator

**Статус:** проект стратегии и discovery recommendation; NOT READY for pilot / investment approval.  
**Human gate 1:** пользователь выбрал B — семейные группы (2026-11-22).  
**Human gate 2:** не пройден; решение после пилота не получено.

## Решение в одном абзаце

Проверять первым семейный сценарий: участник добровольно разрешает показ остатка; при подтверждённом низком остатке организатор получает минимальное уведомление и может перейти к существующей операции выделения интернета. Это выбранное направление для дальнейшего исследования, а не доказанный лучший сегмент и не обещание, что функция уже реализована.

## Почему B — пока только гипотеза

Учебная доступная база семей — 100k домохозяйств против 40k владельцев нескольких номеров; на части тарифов уже существует операция выделения объёма (CL-002, CL-003, CL-007). Но неизвестны частота/тяжесть проблем, своевременность сигнала, доля причин «исчерпание пакета», стоимость решения и инкрементальные оплаченные месяцы (CL-013, CL-014).

## Что должно быть правдой

- Событие низкого остатка достоверно и приходит до ограничения.
- Участник понимает разрешение и может отозвать его; после отзыва доступ прекращается.
- Организатор имеет право, совместимый тариф и свободный объём.
- Операция исполняется без дублей и подтверждается системой.
- Пилот показывает улучшение outcome относительно контроля без ухудшения guardrails.
- Инкрементальная прибыль покрывает прямые затраты.

## Критические риски

- Неправильный trigger (например, неоплата вместо исчерпания пакета).
- Недоверие/страх слежки — пока гипотеза, требуется проверка.
- Нарушение consent, раскрытие push на экране блокировки, повторная операция.
- Слабый поток событий и отрицательная экономика.

## Следующие шаги

1. Разобрать причины перебоев и оценить частоту по двум сегментам.
2. Проверить качество и задержку данных, тарифную совместимость, consent/revoke.
3. Провести интервью-реконструкции и usability tests коммуникации.
4. Подтвердить владельцев систем, ресурсы и полную стоимость.
5. Рассчитать дизайн пилота после получения baseline; только затем вынести отдельное решение на Human gate 2.

## Финансовая граница

Разрыв 6 млн руб. при учебной ставке 500 руб. за дополнительный оплаченный месяц соответствует 12k дополнительных оплаченных месяцев до новых прямых расходов (CL-005, CL-012). Это не прогноз эффекта функции и не расчёт окупаемости без затрат.

## Ограничения доказательств

В кейсе нет интервью, CRM/support/billing extracts, результатов usability/security tests, пилотных данных, фактической стоимости разработки или измерений agent run. Никакие такие данные не моделировались как реальные.

**Рекомендация:** продолжить только ограниченный discovery после отдельного согласования ресурсов и доступа. Не утверждать разработку, пилот или масштабирование по текущему пакету.

## Tool execution evidence (2026-11-22)

- Exact repository parser v1.0 was run on the original 11-page PDF: 11 sections, 4 extracted tables, exit 0, 0 automatic warnings. Merged-cell table extraction still requires visual review; provenance is in `materials/parsed/source_pdf_run.md`.
- `metrics.py check --strict` passed on the primary and second-brief CSV fixtures: exit 0, 0 warnings each.
- Search attempted DDG HTML, DDG Lite and SearXNG but produced no usable results (exit 4). The EDPB page was fetched separately through an official-source fallback; do not present it as a search result.
- Automated tool smoke-run: 13.910 seconds. `cost_log.py` recorded no LLM/API calls and $0.00 LLM usage for that smoke-run only. Manual time and full-agent cost remain unmeasured.
- The second mini-brief is derived from the same source brief; it is not an independent portability benchmark.

## Remaining gates

The strategy approval gate (workflow S11) has not been passed. The post-pilot business gate at the end of Q2 has also not been passed because no pilot was approved or run. Video and jury PDF remain absent.
