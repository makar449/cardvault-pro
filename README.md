# CardVault Pro

Полноценная full-stack версия маркетплейса коллекционных карт: премиальный frontend, backend, SQLite-база, загрузка фото, корзина, избранное, заказы, заявки на продажу, админ-панель и подключаемая онлайн-оплата.

## Что сделано качественно по 7 пунктам

1. **Дизайн и адаптация**
   - Главная страница сделана в премиальном светлом стиле по референсу.
   - Есть адаптация под desktop/tablet/mobile.
   - Карточки товаров, hero, категории, статистика, график, отзывы, формы, drawer-корзина и модальные окна оформлены единым стилем.

2. **Backend**
   - `server.py` поднимает реальный HTTP API.
   - Данные хранятся в SQLite.
   - Есть пользователи, сессии, товары, изображения, корзина, избранное, заказы, заявки, проверки, отзывы, аудит и статусы доставки.

3. **Оплата**
   - Ручной способ оплаты работает сразу: заказ создаётся в базе, товары резервируются, администратор видит заказ и может менять статус оплаты.
   - Stripe Checkout подготовлен через env-переменные `PAYMENT_PROVIDER=stripe`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`.
   - Webhook `/api/payments/stripe/webhook` отмечает заказ как оплаченный после события `checkout.session.completed`.
   - Без реальных ключей эквайринга настоящие банковские списания невозможны — это ограничение любого сайта, а не кода.

4. **Загрузка фото карт**
   - Пользователь может прикрепить фото при продаже карты.
   - Backend проверяет тип файла: PNG/JPG/WEBP.
   - Backend ограничивает размер файла и сохраняет изображения в `/uploads`.
   - Админ видит фото в заявках.

5. **Админ-панель**
   - Открывается по `/admin.html`.
   - Доступ только для пользователя с ролью `admin`.
   - Есть dashboard, управление товарами, создание/редактирование/архивация лотов, просмотр заказов, изменение оплаты/статуса/трек-номера, модерация заявок на продажу и проверку подлинности.

6. **Безопасность**
   - HttpOnly cookie-сессии вместо localStorage-токенов.
   - CSRF защита через `/api/csrf` и `X-CSRF-Token`.
   - Пароли хэшируются PBKDF2-HMAC-SHA256.
   - Есть rate limiting для auth/write/upload запросов.
   - Защитные headers: CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy.
   - Email verification и password reset готовы; SMTP подключается через env.

7. **Реальная структура маркетплейса**
   - Товары имеют продавца, рейтинг, цену, остаток, статус и изображения.
   - Заказы имеют состав, сумму, страховку, статус оплаты, статус доставки, трек-номер и историю событий.
   - Заявки проходят модерацию в админке.
   - Есть audit log для ключевых действий.

## Запуск локально

```bash
cd cardvault_pro
python3 server.py
```

Открыть сайт:

```text
http://localhost:8000
```

Админ-панель:

```text
http://localhost:8000/admin.html
```

Логин администратора по умолчанию:

```text
admin@cardvault.local
CardVaultAdmin2026!
```

Перед продакшеном обязательно поменять `SECRET_KEY`, `INITIAL_ADMIN_EMAIL`, `INITIAL_ADMIN_PASSWORD`.

## Быстрый тест

```bash
cd cardvault_pro
python3 smoke_test.py
```

Тест проверяет запуск сервера, CSRF, вход администратора, корзину, создание заказа и admin dashboard.

## Настройка оплаты Stripe

1. Создайте Stripe аккаунт и получите test/live secret key.
2. Установите env-переменные:

```bash
export PAYMENT_PROVIDER=stripe
export STRIPE_SECRET_KEY=sk_test_...
export STRIPE_WEBHOOK_SECRET=whsec_...
export APP_URL=https://your-domain.com
```

3. Добавьте webhook в Stripe Dashboard на URL:

```text
https://your-domain.com/api/payments/stripe/webhook
```

4. После успешного события `checkout.session.completed` backend обновит заказ до `paid`.

## Настройка email

Для реальной отправки подтверждения email и сброса пароля задайте:

```bash
export SMTP_HOST=smtp.example.com
export SMTP_PORT=587
export SMTP_USER=...
export SMTP_PASSWORD=...
export SMTP_FROM=noreply@your-domain.com
```

Если SMTP не настроен, письма выводятся в лог сервера. В production поставьте `DEV_SHOW_TOKENS=0`.

## Деплой

В комплекте есть:

- `Dockerfile`
- `Procfile`
- `render.yaml`
- `.env.example`

На VPS минимально:

```bash
python3 server.py
```

Для продакшена используйте reverse proxy с HTTPS, например Nginx/Caddy, и выставьте:

```bash
COOKIE_SECURE=1
APP_URL=https://your-domain.com
DEV_SHOW_TOKENS=0
```
