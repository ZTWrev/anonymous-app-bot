# Anonymous Application Bot

Telegram-бот для подачи заявок и анонимного общения.

## Возможности

- **Подача заявок** — пользователи заполняют анкету (имя, причина)
- **Панель администратора** — просмотр, принятие и отклонение заявок
- **Анонимный чат** — общение без раскрытия личности
- **Рассылкa** — `/broadcast <текст>` от админа всем принятым

## Установка

```bash
pip install python-telegram-bot python-dotenv
```

## Настройка

1. Создай бота у [@BotFather](https://t.me/BotFather) и получи токен
2. Узнай свой Telegram ID (например, у @userinfobot)
3. Скопируй `.env.example` в `.env` и заполни:

```
BOT_TOKEN=твой_токен
ADMIN_ID=твой_telegram_id
```

## Запуск

```bash
python3 bot.py
```
