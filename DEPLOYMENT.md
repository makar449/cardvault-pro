# Production checklist для CardVault Pro

1. Купить домен и направить DNS на VPS/Render/Railway/Fly.io.
2. Установить HTTPS. Без HTTPS не включать реальные платежи.
3. Задать env-переменные из `.env.example`.
4. Поменять admin email/password.
5. Поставить `COOKIE_SECURE=1` и `DEV_SHOW_TOKENS=0`.
6. Подключить SMTP для писем.
7. Подключить Stripe или другой эквайринг и проверить webhook.
8. Сделать backup `data/cardvault.sqlite3` по расписанию.
9. Для высоких нагрузок перейти с SQLite на PostgreSQL, но для MVP и первых продаж SQLite достаточно.
