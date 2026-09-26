# Документация и справочные материалы

Здесь хранятся вспомогательные материалы, на которые ссылаются скрипты
(сам генерируемый результат лежит в `output/`, которого нет в репозитории).

## Справочники API UISP

- `export_uisp_topology.py` использует эндпоинты NMS API v2.1:
  - `GET /sites`
  - `GET /devices?withInterfaces=true`
  - `GET /data-links`
  - `GET /devices/ssids`
- `export_crm_clients.py` использует CRM API v1.0 (см. `.env.example`).

Актуальные swagger-описания можно сохранить сюда при необходимости:

```bash
# NMS API (вместо этого файла в docstring упоминается docs/unms-swagger.json)
curl -sk -H "x-auth-token: $NMS_API_TOKEN" \
     "${NMS_API_URL%/}/../swagger.json" -o docs/unms-swagger.json
```

Токен передаётся через переменную окружения, в репозиторий не попадает.
