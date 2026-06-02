Система управления финансами API для учета доходов и расходов с категориями, фильтрацией, сортировкой и автоматическим расчетом баланса.
 нужен Docker и docker compose

1 в папке проекта выполнить;

```bash
docker compose up --build
```

2 в браузере по адресу: `http://localhost:8000/docs`

API

- `POST /categories` - создать категорию
- `GET /categories` - получить список категорий
- `PUT /categories/{id}` - обновить категорию
- `DELETE /categories/{id}` - удалить категорию

- `POST /operations` - создать операцию
- `GET /operations` - получить операции с фильтрами и сортировкой
- `GET /operations/{id}` - получить одну операцию
- `PUT /operations/{id}` - обновить операцию
- `DELETE /operations/{id}` - удалить операцию

- `GET /balance` - расчет баланса (доходы, расходы, остаток)

Фильтрация операций

`GET /operations` поддерживает параметры
- `date_from` - дата начала периода
- `date_to` - дата конца периода
- `category_id` - категория
- `type` - `income` или `expense`
- `sort_by` - `date`, `amount`, `type`, `category`
- `sort_order` - `asc` или `desc`
