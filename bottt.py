import subprocess
import sys
import os
import json
import asyncio
import time
import logging
import psutil
from telethon import TelegramClient, events, Button, types
from telethon.tl.types import ChannelParticipantsAdmins

# Настройка логирования
logging.basicConfig(filename='bot.log', level=logging.INFO, format='%(asctime)s - %(message)s')

# Замените на ваши данные
api_id = '10660752'
api_hash = '9fe01567773a2c41362c6033b0fb113d'
bot_token = '7420605073:AAEvURcOEZzIpk7KF9_B9D0J6DCQKe-WpQY'

print("Initializing bot...")
logging.info("Bot initializing...")

client = TelegramClient('bott', api_id, api_hash).start(bot_token=bot_token)

EMOJI_LIST = ['😀', '😃', '😄', '😁', '😆', '😅', '😂', '🤣', '😊', '😇']
IGNORE_LIST = {}
LAST_MENTION_TIME = {}
MENTION_TASKS = {}
USER_REMOVE_STATE = {}
USER_ADD_STATE = {}
SEND_MESSAGE_STATE = {}
USER_BLOCK_STATE = {}
USER_UNBLOCK_STATE = {}
PROCESS_STATE = {}
ADMINS = ['vsakoe0']
CHATS = {}
BLOCKED_USERS = set()
BLOCKED_CHATS = set()
SPAM_USERS = {}

# Файлы для хранения данных
IGNORE_FILE = 'ignore_list.json'
ADMINS_FILE = 'admins.json'
BLOCKED_USERS_FILE = 'blocked_users.json'
BLOCKED_CHATS_FILE = 'blocked_chats.json'
CHATS_FILE = 'chats.json'
BACKUP_FILE = 'backup.json'

def load_json(file, default):
    if os.path.exists(file):
        try:
            with open(file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            logging.error(f"Ошибка чтения или поврежден файл {file}. Перезапись значением по умолчанию.")
    save_json(file, default)
    return default

def save_json(file, data):
    with open(file, 'w') as f:
        json.dump(data, f)

def load_data():
    global IGNORE_LIST, ADMINS, BLOCKED_USERS, BLOCKED_CHATS, CHATS
    IGNORE_LIST = load_json(IGNORE_FILE, {})
    ADMINS = load_json(ADMINS_FILE, ['vsakoe0'])
    BLOCKED_USERS = set(load_json(BLOCKED_USERS_FILE, []))
    BLOCKED_CHATS = set(load_json(BLOCKED_CHATS_FILE, []))
    CHATS = load_json(CHATS_FILE, {})
    logging.info("Data loaded successfully.")

def save_data():
    save_json(IGNORE_FILE, IGNORE_LIST)
    save_json(ADMINS_FILE, ADMINS)
    save_json(BLOCKED_USERS_FILE, list(BLOCKED_USERS))
    save_json(BLOCKED_CHATS_FILE, list(BLOCKED_CHATS))
    save_json(CHATS_FILE, CHATS)
    logging.info("Data saved successfully.")

def backup_data():
    backup = {
        'IGNORE_LIST': IGNORE_LIST,
        'ADMINS': ADMINS,
        'BLOCKED_USERS': list(BLOCKED_USERS),
        'BLOCKED_CHATS': list(BLOCKED_CHATS),
        'CHATS': CHATS
    }
    save_json(BACKUP_FILE, backup)
    logging.info("Backup created successfully.")

def restore_from_backup():
    try:
        with open(BACKUP_FILE, 'r') as f:
            backup = json.load(f)
            global IGNORE_LIST, ADMINS, BLOCKED_USERS, BLOCKED_CHATS, CHATS
            IGNORE_LIST = backup.get('IGNORE_LIST', {})
            ADMINS = backup.get('ADMINS', ['vsakoe0'])
            BLOCKED_USERS = set(backup.get('BLOCKED_USERS', []))
            BLOCKED_CHATS = set(backup.get('BLOCKED_CHATS', []))
            CHATS = backup.get('CHATS', {})
            save_data()
            logging.info("Data restored successfully from backup.")
            return True
    except (json.JSONDecodeError, IOError):
        logging.error("Failed to restore data from backup.")
        return False

load_data()

async def is_user_admin(chat_id, user_id):
    try:
        admins = await client.get_participants(chat_id, filter=ChannelParticipantsAdmins)
        return any(admin.id == user_id for admin in admins)
    except:
        await client.send_message(chat_id, "😕 У меня нет прав, назначь меня администратором группы.")
        return False

async def mention_all_logic(event):
    chat_id = event.chat_id
    sender = await event.get_sender()

    if event.is_private:
        await event.reply("✋ Эту команду нельзя использовать в личных сообщениях.")
        return

    if sender.id == (await client.get_me()).id:
        return  # Бот не должен реагировать на свои сообщения

    if sender.username in BLOCKED_USERS:
        return

    if not await is_user_admin(chat_id, sender.id):
        await event.reply(f"🚫 <b>{sender.first_name}</b>, у тебя нет прав в этой группе на созывы.", parse_mode='html')
        return

    participants = await client.get_participants(chat_id)
    mentions = [p for p in participants if not p.bot and p.id != sender.id and p.username not in IGNORE_LIST.get(str(chat_id), set())]

    if not mentions:
        await event.reply("🤔 В этом чате некого созывать.", parse_mode='html')
        return

    current_time = time.time()
    if chat_id in LAST_MENTION_TIME and (current_time - LAST_MENTION_TIME[chat_id] < 180):
        if chat_id not in MENTION_TASKS or MENTION_TASKS[chat_id].done():
            LAST_MENTION_TIME.pop(chat_id, None)
        else:
            await event.reply("⏳ Команда запускается не чаще чем раз в 3 минуты.", parse_mode='html')
            return

    LAST_MENTION_TIME[chat_id] = current_time
    task = asyncio.create_task(send_mentions(chat_id, sender.username))
    MENTION_TASKS[chat_id] = task

    await event.reply(f"<b>{sender.first_name}</b> запустил созыв. Используйте <code>/stop</code> или кнопку ниже, чтобы отменить. 🤖", buttons=[Button.inline("Отменить созыв", b'stop_mention')], parse_mode='html')

async def send_mentions(chat_id, initiator):
    await asyncio.sleep(5)

    if chat_id in MENTION_TASKS and MENTION_TASKS[chat_id].cancelled():
        return

    participants = await client.get_participants(chat_id)
    mentions = [f"[{EMOJI_LIST[i % len(EMOJI_LIST)]}](tg://user?id={p.id})" for i, p in enumerate(participants) if not p.bot and p.username and p.username not in IGNORE_LIST.get(str(chat_id), set())]

    if not mentions:
        await client.send_message(chat_id, "🤔 В этом чате некого созывать.", parse_mode='html')
        return

    for i in range(0, len(mentions), 10):
        await client.send_message(chat_id, ' '.join(mentions[i:i+10]), parse_mode='markdown')
        await asyncio.sleep(1)

    MENTION_TASKS.pop(chat_id, None)

@client.on(events.NewMessage(pattern='/start'))
async def on_start(event):
    if not event.is_private:
        return

    sender = await event.get_sender()
    await event.reply(
        f"👋 Привет, {sender.first_name}. Я зазывала. Создан чтобы созвать людей в чатах на мероприятия и сходки. \n"
        "Добавь меня в чат и тогда я буду полезен.",
        buttons=[
            [Button.url("Добавить в чат", "https://t.me/Sozivalala_bot?startgroup=true")],
            [Button.url("Канал поддержки", "t.me/sozivalala")]
        ]
    )

@client.on(events.NewMessage(pattern='/run'))
async def on_run(event):
    if not event.is_private:
        await mention_all_logic(event)

@client.on(events.NewMessage(func=lambda e: not e.is_private and any(trigger in e.raw_text for trigger in ['@a', '@all', '@everyone'])))
async def on_all(event):
    await mention_all_logic(event)

@client.on(events.NewMessage(pattern='/stop'))
async def stop_mention(event):
    user_id = event.sender_id
    chat_id = event.chat_id

    if not await is_user_admin(chat_id, user_id):
        await event.reply("❌ Только администратор может отменить созыв.", parse_mode='html')
        return

    if chat_id in MENTION_TASKS:
        MENTION_TASKS[chat_id].cancel()
        del MENTION_TASKS[chat_id]

    if chat_id in LAST_MENTION_TIME:
        del LAST_MENTION_TIME[chat_id]

    await event.reply("🔕 Созыв остановлен.", parse_mode='html')

@client.on(events.CallbackQuery(data=b'stop_mention'))
async def stop_mention_callback(event):
    await stop_mention(event)

@client.on(events.NewMessage(pattern='/remove'))
async def remove_user_init(event):
    user_id = event.sender_id
    if event.is_private:
        USER_REMOVE_STATE[user_id] = True
        await event.reply(
            "🛑 Вы можете прекратить получать уведомления о созыве из определенных чатов, отправьте мне @username, t.me: или id чата от которого не хотите уведомлений.\n(/cancel для отмены)",
            buttons=[Button.inline("Готово", b'done_remove')]
        )
    else:
        chat_id = event.chat_id
        if str(chat_id) not in IGNORE_LIST:
            IGNORE_LIST[str(chat_id)] = set()
        IGNORE_LIST[str(chat_id)].add(user_id)
        save_data()
        await event.reply(f"🛑 Пользователь <b>{event.sender.first_name}</b> больше не будет получать уведомления о созывах в этом чате.", parse_mode='html')

@client.on(events.NewMessage(func=lambda e: e.is_private and e.sender_id in USER_REMOVE_STATE and not e.raw_text.startswith('/cancel')))
async def remove_user_from_chat(event):
    chat_identifier = event.raw_text.strip()
    try:
        chat = await client.get_entity(chat_identifier)
        chat_id = chat.id
        if str(chat_id) not in CHATS:
            await event.reply("❗ Бот не состоит в этом чате. Попробуйте другой чат.", buttons=[Button.inline("Закрыть", b'close')])
            return
        if str(chat_id) not in IGNORE_LIST:
            IGNORE_LIST[str(chat_id)] = set()
        IGNORE_LIST[str(chat_id)].add(event.sender_id)
        save_data()
        USER_REMOVE_STATE.pop(event.sender_id, None)
        await event.reply(f"✅ Вы больше не будете получать уведомления о созывах в чате {chat.title}.", buttons=[Button.inline("Готово", b'done_remove')])
    except Exception as e:
        await event.reply(f"❗ Это не ссылка/юзернейм на чат. Ошибка: {str(e)}", buttons=[Button.inline("Закрыть", b'close')])

@client.on(events.CallbackQuery(data=b'done_remove'))
async def done_remove(event):
    user_id = event.sender_id
    USER_REMOVE_STATE.pop(user_id, None)
    await event.delete()

@client.on(events.CallbackQuery(data=b'close'))
async def close_message(event):
    await event.delete()

@client.on(events.NewMessage(pattern='/add'))
async def add_user_init(event):
    user_id = event.sender_id
    if event.is_private:
        USER_ADD_STATE[user_id] = True
        await event.reply(
            "✅ Вы можете возобновить получение уведомлений о созыве из определенных чатов, отправьте мне @username, t.me: или id чата в который хотите получать уведомления.\n(/cancel для отмены)",
            buttons=[Button.inline("Готово", b'done_add')]
        )
    else:
        chat_id = event.chat_id
        if str(chat_id) in IGNORE_LIST and user_id in IGNORE_LIST[str(chat_id)]:
            IGNORE_LIST[str(chat_id)].remove(user_id)
            save_data()
            await event.reply(f"✅ Пользователь <b>{event.sender.first_name}</b> теперь получает уведомления о созывах в этом чате.", parse_mode='html')
        else:
            await event.reply("⚠️ Вы и так получаете уведомления о созывах в этом чате.", parse_mode='html')

@client.on(events.NewMessage(func=lambda e: e.is_private and e.sender_id in USER_ADD_STATE and not e.raw_text.startswith('/cancel')))
async def add_user_to_chat(event):
    chat_identifier = event.raw_text.strip()
    try:
        chat = await client.get_entity(chat_identifier)
        chat_id = chat.id
        if str(chat_id) not in CHATS:
            await event.reply("❗ Бот не состоит в этом чате. Попробуйте другой чат.", buttons=[Button.inline("Закрыть", b'close')])
            return
        if str(chat_id) in IGNORE_LIST and event.sender_id in IGNORE_LIST[str(chat_id)]:
            IGNORE_LIST[str(chat_id)].remove(event.sender_id)
            save_data()
            USER_ADD_STATE.pop(event.sender_id, None)
            await event.reply(f"✅ Вы снова будете получать уведомления о созывах в чате {chat.title}.", buttons=[Button.inline("Готово", b'done_add')])
        else:
            await event.reply(f"⚠️ Вы и так получаете уведомления о созывах в чате {chat.title}.", buttons=[Button.inline("Готово", b'done_add')])
    except Exception as e:
        await event.reply(f"❗ Это не ссылка/юзернейм на чат. Ошибка: {str(e)}", buttons=[Button.inline("Закрыть", b'close')])

@client.on(events.CallbackQuery(data=b'done_add'))
async def done_add(event):
    user_id = event.sender_id
    USER_ADD_STATE.pop(user_id, None)
    await event.delete()

@client.on(events.NewMessage(pattern='/cancel'))
async def cancel_action(event):
    user_id = event.sender_id
    if user_id in USER_REMOVE_STATE or user_id in USER_ADD_STATE or user_id in SEND_MESSAGE_STATE:
        USER_REMOVE_STATE.pop(user_id, None)
        USER_ADD_STATE.pop(user_id, None)
        SEND_MESSAGE_STATE.pop(user_id, None)
        PROCESS_STATE.pop(user_id, None)
        await event.delete()

@client.on(events.CallbackQuery(data=b'admin_panel'))
async def admin_panel_back(event):
    user_id = event.sender_id
    if user_id in PROCESS_STATE:
        PROCESS_STATE.pop(user_id, None)
    sender = await event.get_sender()
    if sender.username in ADMINS:
        await show_admin_panel(event)
    await event.delete()

@client.on(events.NewMessage(func=lambda e: e.is_private and not e.raw_text.startswith('/') and not (e.sender_id in USER_REMOVE_STATE or e.sender_id in USER_ADD_STATE or e.sender_id in SEND_MESSAGE_STATE or e.sender_id in USER_BLOCK_STATE or e.sender_id in USER_UNBLOCK_STATE) and not (e.raw_text.startswith('@') or e.raw_text.startswith('t.me/') or e.raw_text.isdigit())))
async def handle_private_message(event):
    await event.reply("Добавь меня в группу, и я буду полезен!", buttons=[Button.url("Добавить в группу", "https://t.me/Sozivalala_bot?startgroup=true")])

@client.on(events.ChatAction)
async def greet_on_addition(event):
    chat = await event.get_chat()
    if chat.id in BLOCKED_CHATS:
        await client.kick_participant(chat.id, 'me')
        return

    if event.user_added or event.user_joined:
        for new_member in event.users:
            if new_member.id == (await client.get_me()).id:
                if chat.id not in CHATS:
                    CHATS[str(chat.id)] = chat.title
                    save_data()
                    await client.send_message(event.chat_id,
                        "👋 Привет! Я бот для созыва людей.\n"
                        "Отправь <code>/run</code> для созыва 📢\n"
                        "Так же я реагирую на <code>@a</code>, <code>@all</code>, <code>@everyone</code> 🤗",
                        parse_mode='html'
                    )

@client.on(events.NewMessage(pattern='/admin'))
async def admin_panel(event):
    if not event.is_private:
        await event.reply("Админ-панель доступна только в личных сообщениях.", parse_mode='html')
        return

    sender = await event.get_sender()
    if sender.username not in ADMINS:
        await event.reply("🚫 У вас нет прав для доступа к админ-панели.", parse_mode='html')
        return

    await show_admin_panel(event)

async def show_admin_panel(event):
    buttons = [
        [Button.inline('Написать в чат', b'send_message'), Button.inline('Список чатов', b'list_chats')],
        [Button.inline('Добавить админа', b'add_admin'), Button.inline('Удалить админа', b'remove_admin')],
        [Button.inline('Заблокировать', b'block'), Button.inline('Разблокировать', b'unblock')],
        [Button.inline('Список заблокированных', b'list_blocked'), Button.inline('Список админов', b'list_admins')],
        [Button.inline('Логи', b'view_logs'), Button.inline('Перезагрузить бота', b'restart_bot')],
        [Button.inline('Проверка нагрузки', b'check_load')],
        [Button.inline('Назад', b'admin_panel')]
    ]

    await event.reply('🔧 Админ-панель', buttons=buttons)

@client.on(events.CallbackQuery(data=b'send_message'))
async def send_message_init(event):
    if not event.is_private:
        await event.respond("Эту команду можно использовать только в личных сообщениях.")
        return

    user_id = event.sender_id
    if user_id in PROCESS_STATE:
        await event.respond("⚠️ Дождитесь завершения текущего процесса.")
        return

    PROCESS_STATE[user_id] = {'state': 'awaiting_chat'}
    await event.respond('✏️ Введите @username, ID или ссылку на чат:', buttons=[Button.inline("Назад", b'admin_panel')])

@client.on(events.NewMessage(func=lambda e: e.is_private and e.sender_id in PROCESS_STATE and PROCESS_STATE[e.sender_id]['state'] == 'awaiting_chat'))
async def get_chat_and_message(event):
    chat_identifier = event.raw_text.strip()
    try:
        chat = await client.get_entity(chat_identifier)
        chat_id = chat.id
        if str(chat_id) not in CHATS:
            await event.reply('❗ Бот не состоит в этом чате. Попробуйте другой чат.', buttons=[Button.inline("Назад", b'admin_panel')])
            return
        PROCESS_STATE[event.sender_id] = {'state': 'awaiting_message', 'chat_id': chat.id, 'chat_name': chat.title}
        await event.reply(f'Теперь вы можете писать в чат {chat.title}. Отправляйте сообщения:', buttons=[Button.inline("Назад", b'admin_panel')])
    except Exception as e:
        await event.reply(f'❗ Это не ссылка/юзернейм на чат. Ошибка: {str(e)}', buttons=[Button.inline("Назад", b'admin_panel')])

@client.on(events.NewMessage(func=lambda e: e.is_private and e.sender_id in PROCESS_STATE and PROCESS_STATE[e.sender_id]['state'] == 'awaiting_message'))
async def send_message_to_chat(event):
    chat_id = PROCESS_STATE[event.sender_id]['chat_id']
    try:
        if event.raw_text.startswith('@') or event.raw_text.startswith('t.me/'):
            return  # Игнорируем сообщение, если это ссылка на чат
        await client.send_message(chat_id, event.raw_text)
        await event.reply('✅ Сообщение отправлено.', buttons=[Button.inline("Назад", b'admin_panel')])
    except Exception as e:
        await event.reply(f'❌ Ошибка: {e}', buttons=[Button.inline("Назад", b'admin_panel')])

@client.on(events.CallbackQuery(data=b'list_chats'))
async def list_chats(event):
    await event.delete()
    if CHATS:
        chat_list = '\n'.join([f"<code>{chat_id}</code>: {chat_title}" for chat_id, chat_title in CHATS.items()])
    else:
        chat_list = "🤖 Бот не добавлен ни в один чат."
    
    await event.reply(f"📃 Чаты с ботом:\n{chat_list}", buttons=[Button.inline("Назад", b'admin_panel')], parse_mode='html')

@client.on(events.CallbackQuery(data=b'add_admin'))
async def add_admin(event):
    sender = await event.get_sender()
    if not event.is_private or sender.username != 'vsakoe0':
        await event.respond("Эту команду можно использовать только в личных сообщениях и только главным администратором.")
        return

    user_id = event.sender_id
    if user_id in PROCESS_STATE:
        await event.respond("⚠️ Дождитесь завершения текущего процесса.")
        return

    PROCESS_STATE[user_id] = {'state': 'adding_admin'}
    await event.respond('👤 Введите @username нового администратора:', buttons=[Button.inline("Назад", b'admin_panel')])
    
    def handler(event_inner):
        return event_inner.is_private and event_inner.sender_id == user_id and PROCESS_STATE.get(user_id, {}).get('state') == 'adding_admin'

    @client.on(events.NewMessage(func=handler))
    async def get_new_admin(event_inner):
        new_admin = event_inner.raw_text.strip()
        try:
            entity = await client.get_entity(new_admin)
            if isinstance(entity, types.User):
                if entity.username in ADMINS:
                    await event_inner.reply(f'⚠️ Пользователь {entity.username} уже является администратором.', buttons=[Button.inline("Назад", b'admin_panel')])
                else:
                    ADMINS.append(entity.username)
                    save_data()
                    await event_inner.reply(f'✅ Админ {entity.username} добавлен.', buttons=[Button.inline("Назад", b'admin_panel')])
            else:
                await event_inner.reply("❌ Это не человек. Отправь данные человека.", buttons=[Button.inline("Назад", b'admin_panel')])
        except ValueError:
            await event_inner.reply("❌ Это не ссылка и не юзернейм. Отправь корректные данные.", buttons=[Button.inline("Назад", b'admin_panel')])

@client.on(events.CallbackQuery(data=b'remove_admin'))
async def remove_admin(event):
    sender = await event.get_sender()
    if not event.is_private or sender.username != 'vsakoe0':
        await event.respond("Эту команду можно использовать только в личных сообщениях и только главным администратором.")
        return

    user_id = event.sender_id
    if user_id in PROCESS_STATE:
        await event.respond("⚠️ Дождитесь завершения текущего процесса.")
        return

    PROCESS_STATE[user_id] = {'state': 'removing_admin'}
    await event.respond('👤 Введите @username администратора для удаления:', buttons=[Button.inline("Назад", b'admin_panel')])
    
    def handler(event_inner):
        return event_inner.is_private and event_inner.sender_id == user_id and PROCESS_STATE.get(user_id, {}).get('state') == 'removing_admin'

    @client.on(events.NewMessage(func=handler))
    async def remove_existing_admin(event_inner):
        admin_to_remove = event_inner.raw_text.strip()
        if admin_to_remove in ADMINS:
            ADMINS.remove(admin_to_remove)
            save_data()
            await event_inner.reply(f'✅ Админ {admin_to_remove} удален.', buttons=[Button.inline("Назад", b'admin_panel')])
        else:
            await event_inner.reply(f'⚠️ Пользователь {admin_to_remove} не является администратором.', buttons=[Button.inline("Назад", b'admin_panel')])

@client.on(events.CallbackQuery(data=b'block'))
async def block_entity_init(event):
    if not event.is_private:
        await event.respond("Эту команду можно использовать только в личных сообщениях.")
        return

    user_id = event.sender_id
    if user_id in PROCESS_STATE:
        await event.respond("⚠️ Дождитесь завершения текущего процесса.")
        return

    PROCESS_STATE[user_id] = {'state': 'blocking'}
    await event.delete()
    await event.respond('🚫 Введите @username или ID чата/пользователя для блокировки:', buttons=[Button.inline("Назад", b'admin_panel')])
    
    USER_BLOCK_STATE[event.sender_id] = True

@client.on(events.CallbackQuery(data=b'unblock'))
async def unblock_entity_init(event):
    if not event.is_private:
        await event.respond("Эту команду можно использовать только в личных сообщениях.")
        return

    user_id = event.sender_id
    if user_id in PROCESS_STATE:
        await event.respond("⚠️ Дождитесь завершения текущего процесса.")
        return

    PROCESS_STATE[user_id] = {'state': 'unblocking'}
    await event.delete()
    await event.respond('🔓 Введите @username или ID чата/пользователя для разблокировки:', buttons=[Button.inline("Назад", b'admin_panel')])
    
    USER_UNBLOCK_STATE[event.sender_id] = True

@client.on(events.CallbackQuery(data=b'list_admins'))
async def list_admins(event):
    await event.delete()
    admins_list = '\n'.join(ADMINS) if ADMINS else "🚫 Список админов пуст."
    await event.reply(f"📜 Администраторы:\n{admins_list}", buttons=[Button.inline("Назад", b'admin_panel')])

@client.on(events.CallbackQuery(data=b'view_logs'))
async def view_logs(event):
    sender = await event.get_sender()
    if sender.username != 'vsakoe0':
        await event.respond("❌ У вас нет прав для просмотра логов.")
        return

    await event.delete()
    try:
        with open('bot.log', 'r') as log_file:
            logs = log_file.readlines()[-10:]  # Последние 10 записей
        log_text = ''.join(logs)
    except IOError:
        log_text = "⚠️ Не удалось загрузить логи."

    await event.reply(f"📜 Последние логи:\n<code>{log_text}</code>", parse_mode='html', buttons=[Button.inline("Назад", b'admin_panel')])

@client.on(events.CallbackQuery(data=b'check_load'))
async def check_load(event):
    sender = await event.get_sender()
    if sender.username != 'vsakoe0':
        await event.respond("❌ У вас нет прав для проверки нагрузки.")
        return

    await event.delete()
    cpu_usage = psutil.cpu_percent(interval=1)
    memory_info = psutil.virtual_memory()
    uptime = time.time() - psutil.boot_time()
    uptime_str = time.strftime("%H:%M:%S", time.gmtime(uptime))

    response = (
        f"🖥️ Нагрузка на бота:\n"
        f"Процессор: {cpu_usage}%\n"
        f"Оперативная память: {memory_info.percent}%\n"
        f"Время работы: {uptime_str}\n"
    )

    await event.reply(response, buttons=[Button.inline("Назад", b'admin_panel')])

async def process_block_or_unblock(event, block=True):
    user_id = event.sender_id
    chat_identifier = event.raw_text.strip()
    action = "заблокирован" if block else "разблокирован"
    try:
        entity = await client.get_entity(chat_identifier)
        if isinstance(entity, types.User):
            if block:
                BLOCKED_USERS.add(entity.username)
            else:
                BLOCKED_USERS.discard(entity.username)
            save_data()
            await event.reply(f"Пользователь {entity.username} {action}.")
        elif isinstance(entity, (types.Chat, types.Channel)):
            if block:
                BLOCKED_CHATS.add(entity.id)
                await client.send_message(entity.id, f"Ваш чат {entity.title} внесён в черный список за нарушение правил. Вы можете написать в поддержку для выявления причин или подачи апелляции.", buttons=[Button.url("Поддержка", "t.me/sozivalala")])
                await client.kick_participant(entity.id, 'me')
            else:
                BLOCKED_CHATS.discard(entity.id)
            save_data()
            await event.reply(f"Чат {entity.title} {action}.")
    except Exception as e:
        await event.reply(f"❗ Это не ссылка/юзернейм на чат или пользователя. Ошибка: {str(e)}")

@client.on(events.NewMessage(func=lambda e: e.is_private and e.sender_id in USER_BLOCK_STATE))
async def block_entity(event):
    await process_block_or_unblock(event, block=True)
    USER_BLOCK_STATE.pop(event.sender_id, None)
    PROCESS_STATE.pop(event.sender_id, None)

@client.on(events.NewMessage(func=lambda e: e.is_private and e.sender_id in USER_UNBLOCK_STATE))
async def unblock_entity(event):
    await process_block_or_unblock(event, block=False)
    USER_UNBLOCK_STATE.pop(event.sender_id, None)
    PROCESS_STATE.pop(event.sender_id, None)

@client.on(events.CallbackQuery(data=b'list_blocked'))
async def list_blocked(event):
    await event.delete()
    blocked_users_list = '\n'.join(BLOCKED_USERS) if BLOCKED_USERS else "🚫 Черный список пользователей пуст."
    blocked_chats_list = '\n'.join(map(str, BLOCKED_CHATS)) if BLOCKED_CHATS else "🚫 Черный список чатов пуст."
    
    await event.reply(f"📜 Заблокированные пользователи:\n{blocked_users_list}\n📜 Заблокированные чаты:\n{blocked_chats_list}", buttons=[Button.inline("Назад", b'admin_panel')])

@client.on(events.CallbackQuery(data=b'restart_bot'))
async def restart_bot(event):
    sender = await event.get_sender()
    if sender.username == 'vsakoe0':
        await event.respond("🔄 Перезагрузка бота...")
        os.execv(sys.executable, ['python'] + sys.argv)
    else:
        await event.respond("❌ У вас нет прав для перезагрузки бота.", buttons=[Button.inline("Назад", b'admin_panel')])

# Обработчик создания и отправки бэкапов
@client.on(events.NewMessage(pattern='/backup'))
async def send_backup(event):
    sender = await event.get_sender()
    if sender.username == 'vsakoe0':
        backup_data()
        await client.send_file(sender.id, BACKUP_FILE, caption="🗂 Бэкап данных")
    else:
        await event.reply("❌ У вас нет прав для создания бэкапа.")

@client.on(events.NewMessage(pattern='/restore'))
async def restore_backup(event):
    sender = await event.get_sender()
    if sender.username == 'vsakoe0':
        if restore_from_backup():
            await event.reply("✅ Данные успешно восстановлены из бэкапа.")
        else:
            await event.reply("❌ Не удалось восстановить данные из бэкапа.")
    else:
        await event.reply("❌ У вас нет прав для восстановления данных.")

print("Bot is running...")
logging.info("Bot is running...")
client.run_until_disconnected()