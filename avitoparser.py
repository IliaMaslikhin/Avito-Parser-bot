from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import telebot
import time
import json
import threading
import logging
from telebot import types  # Для кнопок

logging.basicConfig(level=logging.INFO)


# Класс для парсинга Avito
class AvitoParser:
    def __init__(self, bot, chat_id, url):
        self.url = url
        self.bot = bot
        self.chat_id = chat_id
        self.first_ad_time = None  # Время первого объявления
        self.driver = None

    def start_driver(self):
        options = webdriver.ChromeOptions()
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--headless')  # Запуск в headless режиме для производительности
        self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    def parse(self):
        if not self.driver:
            self.start_driver()
        wait = WebDriverWait(self.driver, 10)

        while True:
            self.driver.get(self.url)
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div.iva-item-root-_lk9K')))
                ads = self.driver.find_elements(By.CSS_SELECTOR, 'div.iva-item-root-_lk9K')
            except Exception as e:
                logging.error(f"Ошибка загрузки страницы: {e}")
                break

            if ads:
                # Получаем данные самого первого объявления (дата и время размещения)
                ad = ads[0]
                try:
                    time_posted = ad.find_element(By.CSS_SELECTOR, 'p[data-marker="item-date"]').text.strip()
                except NoSuchElementException:
                    time_posted = None

                # Если это первое объявление, запоминаем время публикации
                if self.first_ad_time is None:
                    self.first_ad_time = time_posted
                    logging.info(f"Время первого объявления запомнено: {time_posted}")
                # Если время нового объявления отличается, отправляем уведомление
                elif time_posted != self.first_ad_time:
                    try:
                        title = ad.find_element(By.CSS_SELECTOR, 'h3.styles-module-root-W_crH').text.strip()
                        price = ad.find_element(By.CSS_SELECTOR, 'p[data-marker="item-price"]').text.strip()
                        link = ad.find_element(By.CSS_SELECTOR, 'a[data-marker="item-title"]').get_attribute('href')
                    except NoSuchElementException:
                        title = "Неизвестное объявление"
                        price = "Цена не указана"
                        link = None

                    self.first_ad_time = time_posted  # Обновляем запомненное время
                    self.bot.send_message(self.chat_id,
                                          f"Новое объявление: {title}, Цена: {price}, Время: {time_posted}, Ссылка: {link}")

            time.sleep(60)  # Ожидание между проверками

    def stop_driver(self):
        if self.driver:
            self.driver.quit()
            self.driver = None


# Конфигурация бота
TOKEN = ''
bot = telebot.TeleBot(TOKEN)
user_data = {}


def load_user_data():
    global user_data
    try:
        with open('user_data.txt', 'r') as file:
            user_data = json.load(file)
    except FileNotFoundError:
        user_data = {}


def save_user_data():
    with open('user_data.txt', 'w') as file:
        json.dump(user_data, file)


# Команды для управления ботом
@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("Добавить ссылку")
    btn2 = types.KeyboardButton("Список ссылок")
    btn3 = types.KeyboardButton("Удалить ссылку")
    markup.add(btn1, btn2, btn3)
    bot.send_message(message.chat.id, "Привет! Выберите действие:", reply_markup=markup)
    logging.info(f"Received /start command from {message.chat.id}")


# Добавление ссылки через кнопку
@bot.message_handler(func=lambda message: message.text == "Добавить ссылку")
def add_url_prompt(message):
    bot.send_message(message.chat.id, "Отправь мне ссылку на отслеживание.")
    bot.register_next_step_handler(message, add_url)


def add_url(message):
    url = message.text
    user_id = message.chat.id
    if user_id not in user_data:
        user_data[user_id] = []
    if url not in user_data[user_id]:
        user_data[user_id].append(url)
        bot.send_message(user_id, "Ссылка добавлена.")
        logging.info(f"Added URL {url} for user {user_id}")
        save_user_data()
        start_parsing(user_id, url)  # Запускаем парсинг сразу после добавления ссылки
    else:
        bot.send_message(user_id, "Ссылка уже отслеживается.")
        logging.info(f"URL {url} already being tracked for user {user_id}")


# Просмотр списка ссылок
@bot.message_handler(func=lambda message: message.text == "Список ссылок")
def list_urls(message):
    user_id = message.chat.id
    if user_id in user_data and user_data[user_id]:
        urls = "\n".join(user_data[user_id])
        bot.send_message(user_id, f"Ссылки, которые вы отслеживаете:\n{urls}")
    else:
        bot.send_message(user_id, "Нет добавленных ссылок для отслеживания.")


# Удаление ссылки через кнопку
@bot.message_handler(func=lambda message: message.text == "Удалить ссылку")
def delete_url_prompt(message):
    bot.send_message(message.chat.id, "Отправь ссылку, которую нужно удалить.")
    bot.register_next_step_handler(message, delete_url)


def delete_url(message):
    url = message.text
    user_id = message.chat.id
    if user_id in user_data and url in user_data[user_id]:
        user_data[user_id].remove(url)
        bot.send_message(user_id, "Ссылка удалена.")
        logging.info(f"Deleted URL {url} for user {user_id}")
        save_user_data()
    else:
        bot.send_message(user_id, "Эта ссылка не отслеживается.")


# Автоматический парсинг при добавлении ссылки
def start_parsing(user_id, url):
    parser = AvitoParser(bot, user_id, url)
    thread = threading.Thread(target=parser.parse)
    thread.start()


# Запуск бота
load_user_data()
bot.polling()










