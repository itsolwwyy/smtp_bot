from aiogram import Bot, Dispatcher, types, executor
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.storage import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv
from email.message import EmailMessage
import os, logging, smtplib, sqlite3, time, random

load_dotenv('.env')

bot = Bot(os.environ.get('token'))
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
logging.basicConfig(level=logging.INFO)

database = sqlite3.connect('smtp.db')
cursor = database.cursor()
cursor.execute("""CREATE TABLE IF NOT EXISTS users(
    user_id INT,
    chat_id INT,
    username VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    phone VARCHAR(200),
    email VARCHAR(200),
    verifed BOOLEAN,
    created VARCHAR(100)
);
""")
cursor.connection.commit()

inline_keyboards = [
    InlineKeyboardButton('Отправить сообщение', callback_data='send_button'),
    InlineKeyboardButton('Наш сайт', url='https://geeks.kg')
]
inline_button = InlineKeyboardMarkup().add(*inline_keyboards)

@dp.message_handler(commands='start')
async def start(message:types.Message):
    cursor.execute(f"SELECT * FROM users WHERE user_id = {message.from_user.id};")
    result = cursor.fetchall()
    if result == []:
        cursor.execute(f"""INSERT INTO users (user_id, chat_id, username, first_name,
                    last_name, verifed, created) VALUES ({message.from_user.id},
                    {message.chat.id}, '{message.from_user.username}',
                    '{message.from_user.first_name}', 
                    '{message.from_user.last_name}',
                    False,
                    '{time.ctime()}');
                    """)
    cursor.connection.commit()
    await message.answer('Привет! Я помогу тебе отправить сообщение на почту\nНапиши /send', reply_markup=inline_button)

@dp.callback_query_handler(lambda call:call)
async def all_inline(call):
    if call.data == 'send_button':
        await send_command(call.message) 

#to_email, subject, message
class EmailState(StatesGroup):
    to_email = State()
    subject = State()
    message = State()

@dp.message_handler(commands='send')
async def send_command(message:types.Message):
    await message.answer('Введите почту на которую нужно отправить сообщение')
    await EmailState.to_email.set()

@dp.message_handler(state=EmailState.to_email)
async def get_subject(message:types.Message, state:FSMContext):
    await state.update_data(to_email=message.text)
    await message.answer('Введите заголовок')
    await EmailState.subject.set()

@dp.message_handler(state=EmailState.subject)
async def get_message(message:types.Message, state:FSMContext):
    await state.update_data(subject=message.text)
    await message.answer('Введите сообщение')
    await EmailState.message.set()

@dp.message_handler(state=EmailState.message)
async def send_message(message:types.Message, state:FSMContext):
    await state.update_data(message=message.text)
    await message.answer('Отправляем почту...')
    res = await storage.get_data(user=message.from_user.id)
    sender = os.environ.get('smtp_email')
    password = os.environ.get('smtp_email_password')

    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()

    msg = EmailMessage()
    msg.set_content(res['message'])

    msg['Subject'] = res['subject']
    msg['From'] = os.environ.get('smtp_email')
    msg['To'] = res['to_email']

    try:
        server.login(sender, password)
        server.send_message(msg)
        await message.answer('Успешно отправлено!')
    except Exception as error:
        await message.answer(f'Произошла ошибка попробуйте позже\n{error}')
        await state.finish()

class VerifyState(StatesGroup):
    email = State()
    random_code = State()
    code = State()

@dp.message_handler(commands='verifed')
async def get_verifed_code(message:types.Message):
    await message.answer('Введите почту для верификации')
    await VerifyState.email.set()

@dp.message_handler(state=VerifyState.email)
async def send_verify_code(message:types.Message, state:FSMContext):
    await message.answer('Рправляем код верификации...')
    random_code = random.randint(111111, 999999)
    await state.update_data(email=message.text)
    await state.update_data(random_code=random_code)
    sender = os.environ.get('smtp_email')
    password = os.environ.get('smtp_email_password')

    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()

    msg = EmailMessage()
    msg.set_content(f'Здраствуйте ваш код для верификации {random_code}')

    msg['Subject'] = 'Код верификации'
    msg['From'] = os.environ.get('smtp_email')
    msg['To'] = message.text

    try:
        server.login(sender, password)
        server.send_message(msg)
        await message.answer('Успешно отправлено!')
    except Exception as error:
        await message.answer(f'Произошла ошибка попробуйте позже\n{error}')
        await message.answer('Введите код  верификации...')
        await VerifyState.code.set()  

@dp.message_handler(state=VerifyState.code)
async def check_verify_code(message:types.Message, state:FSMContext):
    await message.reply('Начинаю проверку кода...')
    result = await storage.get_data(user=message.from_user.id)
    print(result)
    if result['random_code'] == int(message.text):
        await message.answer('Ок')
        user_email = result['email']
        cursor.execute(f"UPDATE users SET email = '{user_email}', verify = True WHERE user_id = {message.from_user.id};")
        cursor.connection.commit()
    else:
        await message.answer('Неправильный код') 

executor.start_polling(dp)