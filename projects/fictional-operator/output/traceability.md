# Traceability index — fictional-operator

## Evidence IDs из research.md → claim IDs из claims.jsonl

| Evidence | Claim ID | Использование |
|---|---|---|
| E-01 | CL-001, CL-002, CL-003 | Контекст вымышленного кейса и два клиентских сценария; exact segment choice требует сравнения |
| E-02 | CL-007 | Существующая операция выделения интернет-объёма |
| E-03 | CL-008 | Неоплата может объяснять перебой вместо исчерпания пакета |
| E-04 | CL-010 | Номер не подтверждает состояние устройства |
| E-05 | CL-009 | Раздельные разрешения, отзыв согласия, платежные права |
| E-06 | CL-002, CL-003 | Доступные базы сегментов |
| E-07 | CL-005, CL-006 | Baseline/plan-year показатели и цели |
| E-08 | CL-005, CL-006 | Разрыв между baseline и целями |
| E-09 | CL-017 | Определения active group и 14-day activation |
| E-10 | CL-012 | Экономическая ставка и порог 12k paid months |
| E-11 | CL-011 | Рандомизация на уровне семейной группы и одинаковое наблюдение |
| E-12 | CL-016 | Ресурсные ограничения и неподтверждённый QA |

## Правило использования

- `E-xx` — ссылка на фрагмент исходного брифа в `output/research.md`.
- `CL-xxx` — стабильный claim в `state/claims.jsonl`.
- В output-документах приводить оба ID, если вывод синтезирует evidence.
- Hypothesis/forecast не повышать до fact без нового источника и обновления claims.
- Для каждого нового источника добавлять provenance и claim IDs; старые claims не удалять, а переводить в `outdated` / `retracted` при необходимости.

| E-13 | CL-018 | External GDPR consent guidance; applicability to the fictional operator is not established |
