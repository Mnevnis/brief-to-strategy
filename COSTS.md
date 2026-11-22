# COSTS — расходы и время

Обновлено: 2026-11-22T17:31:23.790868+00:00 · лимит: $5.0 · записано: $0.00

**Scope:** `cost_log.py` зарегистрировал отсутствие вызовов модели в tool smoke run. Это не означает, что полный агентный прогон, ручная работа или CI имеют нулевую стоимость.

## Регистрация расходов

Перед платным вызовом:

    python hooks/cost_log.py preflight --project <project> --model <model> --tin <input_tokens> --tout <max_output_tokens>

После вызова:

    python hooks/cost_log.py log --project <project> --run <run-id> --step <step> --model <model> --tin <input_tokens> --tout <output_tokens> --sec <seconds> --id <unique-call-id> --estimate

## Итого по прогонам

| Прогон | Шагов с LLM usage | Время модели | Стоимость, $ | Estimate-записей |
|---|---:|---:|---:|---:|
| tool-smoke-2026-11-22 | 0 | 0 s | 0.000000 | 0 |

## По вызовам

Записей нет: smoke-run не вызывал LLM/API.

## Внешние расходы и ручное время

| Категория | Количество / время | Стоимость | Статус |
|---|---:|---:|---|
| Search/fetch | 1 поиск + 1 fetch | Не измерена | Search exit 4; fetch успешен |
| CI runner | 13.910 s автоматического smoke-run | Не измерена | GitHub Actions billing не проверялся |
| Ручная подготовка и ревью | Не измерено | Не измерена | Нет time-tracking записи |

## Методика

- $0.00 — сумма зарегистрированных LLM/API вызовов в этом smoke-run, не общая стоимость работы.
- Нет usage — не создавать фиктивную estimate-запись.
- Тарифы в `hooks/cost_log.py` необходимо сверять с тарифами провайдера.
- Ручное время, поиск и страницы не включаются в сумму LLM автоматически.
