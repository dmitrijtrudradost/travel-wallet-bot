# Инструкции проекта: Exchangerate.host API

Источник: [документация APILayer](https://docs.apilayer.com/exchangerate/docs/api-documentation), OpenAPI `ExchangeratehostAPI` 1.0.0 (`https://api.swaggerhub.com/apis/apilayer-863/ExchangeratehostAPI/1.0.0/swagger.json`), Quickstart и Code Examples. Контракт запросов и ответов — OpenAPI и примеры кода. Обзорная страница и Quickstart расходятся со спецификацией (`symbols`/`base`/`rates`); их не использовать.

## Тариф этого проекта

На аккаунте включено только следующее:

- ежедневное обновление курсов;
- исторические курсы;
- HTTPS.

Закрыто, вызов даёт `403 function_access_restricted` или `403 source_currency_access_restricted`:

- обновление чаще раза в сутки (hourly, 10 минут, 60 секунд);
- смена базовой валюты (`source`);
- конвертация (`/convert`);
- курсы за период (`/timeframe`);
- изменение курса (`/change`);
- bid/ask (`spread`).

В коде этого проекта вызывать только `GET /live` и `GET /historical`. Базовая валюта всегда `USD`: параметр `source` не передавать. Конвертацию суммы считать локально: `сумма * quotes["USD" + код]`. Динамику за несколько дней собирать отдельными запросами `/historical`, а не `/timeframe` и не `/change`.

## Назначение

REST API курсов валют. Базовый URL: `https://api.exchangerate.host`. Только HTTPS и GET. Ответ — JSON. Значение курса — midpoint. Покрытие: фиат, драгметаллы и криптовалюты (в обзоре 170+, в OpenAPI — 174). Исторические данные — с 1999 года; у новых валют и крипты данные есть только с даты появления. `/live` на этом тарифе обновляется раз в сутки.

## Секреты

Ключ лежит в `.env` в переменной `API_KEY_EXCHANGE`. Читать его только из окружения. Не записывать значение в код, логи, ответы, коммиты и этот файл. В URL передавать как query-параметр `access_key`. Ключ обязателен на каждом запросе.

## Правила интеграции

- Проверять `success`. При `success: false` читать `error.code`, `error.type`, `error.info` и не разбирать поля успешного ответа.
- Параметр `source` не передавать. Базовая валюта ответа всегда `USD`.
- Фильтр валют — `currencies` (коды через запятую, например `EUR,GBP`). Параметров `base` и `symbols` нет.
- Курсы лежат в `quotes`. Ключ пары — `USD` плюс код цели: для GBP это `USDGBP`. Поля `rates` в спецификации нет.
- Даты только `YYYY-MM-DD`.
- `format=1` — только для отладки (pretty JSON). `callback` (JSONP) не использовать. `spread` не передавать.
- Не вызывать `/convert`, `/timeframe`, `/change`, `/list`.
- Не вызывать устаревшие пути старого открытого API: `/latest`, `/symbols`, `/{date}`, `/timeseries`, `/fluctuation`.

## Разрешённые эндпоинты

### `GET /live` — последний дневной курс

Параметры: `access_key` (обяз.), `currencies`. Курс на этом тарифе обновляется раз в сутки.

```json
{"success": true, "timestamp": 1430401802, "source": "USD", "quotes": {"USDEUR": 0.918019, "USDGBP": 0.650364}}
```

### `GET /historical` — курс на дату

Параметры: `access_key`, `date` (обяз., `YYYY-MM-DD`), `currencies`.

Ответ как у `/live`, плюс `historical: true` и `date`. Дата раньше появления валюты даёт `currency_not_available_on_date`, а не пустой список. Если в одном запросе смешаны доступная и ещё недоступная валюта, падает весь запрос.

## Закрытые эндпоинты

В спецификации есть, на этом тарифе не вызывать:

- `GET /convert` — конвертация суммы (`from`, `to`, `amount`);
- `GET /timeframe` — курсы за период (`start_date`, `end_date`, не длиннее 365 дней);
- `GET /change` — изменение курса (`start_rate`, `end_rate`, `change`, `change_pct`).

## Ошибки

HTTP-статус сопровождает тело `{"success": false, "error": {"code", "type", "info"}}`.

| HTTP | type | code | Смысл |
| --- | --- | --- | --- |
| 401 | `missing_access_key`, `invalid_access_key` | 101 | Нет ключа или ключ неверный |
| 401 | `inactive_user` | 102 | Пользователь неактивен |
| 401 | `account_on_hold` | 107 | Есть неоплаченные счета |
| 403 | `function_access_restricted`, `https_access_restricted` | 105 | Функция или HTTPS недоступны на тарифе |
| 403 | `source_currency_access_restricted` | 403 | Нельзя менять `source` |
| 403 | `spread_access_restricted` | 403 | Нельзя запрашивать bid/ask |
| 403 | `api_access_blocked` | 104 | Доступ временно отключён |
| 404 | `invalid_api_function`, `404_not_found` | 103 / 404 | Несуществующий метод |
| 429 | `usage_limit_reached`, `daily_usage_limit_reached`, `fair_use_limit_reached` | 104 | Исчерпан лимит |
| 429 | `rate_limit_reached` | 106 | Слишком частые запросы |
| 500 | `internal_error` | 0 | Ошибка сервера |
| 503 | `maintenance_mode` | 503 | Обслуживание |

Типичные 400: `invalid_source_currency`, `invalid_currency_codes`, `invalid_from_currency`, `invalid_to_currency`, `invalid_conversion_amount`, `no_date_supplied`, `invalid_date`, `no_timeframe_supplied`, `invalid_start_date`, `invalid_end_date`, `invalid_time_frame`, `time_frame_too_long`, `currency_not_available_on_date`.

Повторять запрос имеет смысл при 429 и 503, с паузой. При 401 и 403 повтор без смены ключа или тарифа бесполезен.
