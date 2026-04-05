#!/usr/bin/env python3
"""
MangaBuff Club AutoCheck Bot
Отдельный бот — только авточек клуба:
- Проверяет карту клуба каждые N секунд
- Если карта есть — жертвует автоматически
- Управление аккаунтами и прокси
"""

import os
from pydoc import html
import sys
import json
import time
import re
import threading
import traceback
import requests
from pathlib import Path
from datetime import datetime

try:
    import telebot
    from telebot import types
except ImportError:
    print("❌ pip install pyTelegramBotAPI")
    sys.exit(1)

# ============================================================
# КОНФИГ
# ============================================================
CONFIG_FILE = Path(__file__).parent / "config_check.json"
ACCOUNTS_FILE = Path(__file__).parent / "accounts.json"

BOT_TOKEN = ""  # Укажи свой токен бота

config = {}


def load_config():
    global config
    if CONFIG_FILE.exists():
        try:
            config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except:
            config = {}
    config.setdefault("bot_token", BOT_TOKEN)
    config.setdefault("club_slug", "")
    config.setdefault("club_account_name", "")
    config.setdefault("check_interval", 30)  # секунд между проверками


def save_config():
    CONFIG_FILE.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ============================================================
# АККАУНТЫ
# ============================================================
def load_accounts():
    if not ACCOUNTS_FILE.exists():
        return []
    try:
        data = json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        return []
    except:
        return []


def save_accounts(accounts):
    ACCOUNTS_FILE.write_text(
        json.dumps(accounts, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ============================================================
# MangaBuff API — ТОЧНАЯ КОПИЯ ИЗ РАБОЧЕГО БОТА
# ============================================================
class MangaBuffAPI:
    BASE_URL = "https://mangabuff.ru"

    def __init__(self, account_data: dict):
        self.account = account_data
        self._use_cffi = False
        self._setup_session()

    def _setup_session(self):
        acc_name = self.account.get("name", "unknown")
        seed = hash(acc_name)

        os_profiles = [
            ("Windows NT 10.0; Win64; x64", '"Windows"', 55),
            ("Windows NT 10.0; Win64; x64", '"Windows"', 15),
            ("Macintosh; Intel Mac OS X 10_15_7", '"macOS"', 18),
            ("X11; Linux x86_64", '"Linux"', 7),
            ("X11; Ubuntu; Linux x86_64", '"Linux"', 5),
        ]
        chrome_profiles = [
            ("120", "120.0.6099.110", "chrome120", 15),
            ("120", "120.0.6099.225", "chrome120", 10),
            ("124", "124.0.6367.91", "chrome124", 15),
            ("124", "124.0.6367.207", "chrome124", 10),
            ("131", "131.0.6778.85", "chrome131", 20),
            ("131", "131.0.6778.204", "chrome131", 15),
            ("131", "131.0.6778.109", "chrome131", 15),
        ]

        os_profile = os_profiles[seed % len(os_profiles)]
        chrome_profile = chrome_profiles[(seed >> 8) % len(chrome_profiles)]

        os_string = os_profile[0]
        platform = os_profile[1]
        chrome_ver = chrome_profile[0]
        chrome_full = chrome_profile[1]
        impersonate = chrome_profile[2]

        ua = f"Mozilla/5.0 ({os_string}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_full} Safari/537.36"

        try:
            from curl_cffi.requests import Session as CffiSession

            self.session = CffiSession(impersonate=impersonate)
            self._use_cffi = True
        except ImportError:
            self.session = requests.Session()
            self._use_cffi = False

        # Прокси
        proxy_host = self.account.get("proxy_host", "")
        proxy_port = self.account.get("proxy_port", "")
        proxy_user = self.account.get("proxy_user", "")
        proxy_pass = self.account.get("proxy_pass", "")

        if proxy_host and proxy_port:
            if proxy_user and proxy_pass:
                proxy_url = (
                    f"http://{proxy_user}:{proxy_pass}@{proxy_host}:{proxy_port}"
                )
            else:
                proxy_url = f"http://{proxy_host}:{proxy_port}"
            self.session.proxies = {"http": proxy_url, "https": proxy_url}

        # Headers
        not_a_brand_map = {
            "120": '"Not_A Brand";v="8"',
            "124": '"Not-A.Brand";v="99"',
            "131": '"Not)A;Brand";v="99"',
        }
        not_a_brand = not_a_brand_map.get(chrome_ver, '"Not_A Brand";v="8"')

        accept_langs = [
            "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "ru,en-US;q=0.9,en;q=0.8",
            "ru-RU,ru;q=0.9",
            "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,uk;q=0.6",
            "ru-RU,ru;q=0.9,en;q=0.8",
        ]
        accept_lang = accept_langs[(seed >> 16) % len(accept_langs)]
        accept_enc = (
            "gzip, deflate, br, zstd" if int(chrome_ver) >= 123 else "gzip, deflate, br"
        )

        headers = {
            "sec-ch-ua": f'"Chromium";v="{chrome_ver}", "Google Chrome";v="{chrome_ver}", {not_a_brand}',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": platform,
            "upgrade-insecure-requests": "1",
            "user-agent": ua,
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "sec-fetch-site": "none",
            "sec-fetch-mode": "navigate",
            "sec-fetch-user": "?1",
            "sec-fetch-dest": "document",
            "accept-encoding": accept_enc,
            "accept-language": accept_lang,
        }
        if int(chrome_ver) >= 128:
            headers["priority"] = "u=0, i"
        if (seed >> 24) % 10 == 0:
            headers["dnt"] = "1"

        self.session.headers.update(headers)

        self._chrome_ver = chrome_ver
        self._sec_ch_ua = headers["sec-ch-ua"]
        self._accept_lang = accept_lang
        self._platform = platform

        # Куки
        cookies = self.account.get("cookies", "")
        if cookies:
            if isinstance(cookies, str):
                if cookies.startswith("["):
                    try:
                        cookies = json.loads(cookies)
                    except:
                        cookies = []
                else:
                    cookie_list = []
                    for c in cookies.split("; "):
                        if "=" in c:
                            name, value = c.split("=", 1)
                            cookie_list.append(
                                {"name": name.strip(), "value": value.strip()}
                            )
                    cookies = cookie_list

            if isinstance(cookies, list):
                for c in cookies:
                    name = c.get("name", "")
                    value = c.get("value", "")
                    domain = c.get("domain", "mangabuff.ru")
                    if domain.startswith("."):
                        domain = domain[1:]
                    if name:
                        self.session.cookies.set(name, value, domain=domain)

    def check_auth(self):
        try:
            resp = self._get(f"{self.BASE_URL}/")
            if resp.status_code == 200:
                html = resp.text
                match = re.search(r'data-userid="(\d+)"', html)
                if match:
                    return True, match.group(1)
                if (
                    "Выйти" in html
                    or "logout" in html.lower()
                    or "header__user" in html
                ):
                    match = re.search(r"/users/(\d+)", html)
                    uid = match.group(1) if match else ""
                    return True, uid
            return False, None
        except Exception as e:
            return False, str(e)

    def _get_csrf_from_cookies(self):
        from urllib.parse import unquote

        try:
            val = self.session.cookies.get("XSRF-TOKEN") or self.session.cookies.get(
                "xsrf-token"
            )
            if val:
                return unquote(val)
        except:
            pass
        try:
            for cookie in self.session.cookies:
                name = (
                    cookie if isinstance(cookie, str) else getattr(cookie, "name", "")
                )
                if name.upper() == "XSRF-TOKEN":
                    value = (
                        self.session.cookies[name]
                        if isinstance(cookie, str)
                        else cookie.value
                    )
                    return unquote(value)
        except:
            pass
        return ""

    def _get_headers_with_csrf(self, referer=""):
        csrf = self._get_csrf_from_cookies()
        return {
            "accept": "application/json, text/plain, */*",
            "accept-language": self._accept_lang,
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "origin": self.BASE_URL,
            "referer": referer or f"{self.BASE_URL}/",
            "sec-ch-ua": self._sec_ch_ua,
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": self._platform,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "x-requested-with": "XMLHttpRequest",
            "x-xsrf-token": csrf,
        }

    def _get(self, url, referer="", timeout=15):
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "sec-ch-ua": self._sec_ch_ua,
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": self._platform,
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-origin" if referer else "none",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
        }
        if referer:
            headers["referer"] = referer
        return self.session.get(url, headers=headers, timeout=timeout)

    def _post(self, url, data, referer="", timeout=15):
        headers = self._get_headers_with_csrf(referer)
        if isinstance(data, str):
            pass
        return self.session.post(url, data=data, headers=headers, timeout=timeout)

    def login(self, email, password):
        """HTTP-логин: GET /login -> CSRF -> POST /login -> проверка"""
        try:
            resp = self._get(f"{self.BASE_URL}/login")
            if resp.status_code != 200:
                return False, f"GET /login: HTTP {resp.status_code}"

            csrf = self._get_csrf_from_cookies()
            if not csrf:
                return False, "CSRF токен не найден"

            time.sleep(1.5)

            login_data = {"email": email, "password": password, "remember": "on"}
            resp = self._post(
                f"{self.BASE_URL}/login",
                data=login_data,
                referer=f"{self.BASE_URL}/login",
            )

            if resp.status_code in (200, 302):
                time.sleep(1)
                check_resp = self._get(
                    f"{self.BASE_URL}/", referer=f"{self.BASE_URL}/login"
                )
                if check_resp.status_code == 200:
                    html = check_resp.text
                    user_id = None
                    m = re.search(r'data-userid="(\d+)"', html)
                    if m:
                        user_id = m.group(1)
                    if not user_id:
                        m = re.search(r'/users/(\d+)"', html)
                        if m:
                            user_id = m.group(1)
                    if not user_id and ("header__user" in html or "/logout" in html):
                        m = re.search(r"/users/(\d+)", html)
                        if m:
                            user_id = m.group(1)

                    if user_id:
                        cookies = []
                        try:
                            for name, value in self.session.cookies.items():
                                cookies.append(
                                    {
                                        "name": name,
                                        "value": value,
                                        "domain": "mangabuff.ru",
                                    }
                                )
                        except:
                            pass
                        return True, {"user_id": user_id, "cookies": cookies}
                    else:
                        return False, "Авторизация не подтверждена"
            else:
                return False, f"HTTP {resp.status_code}"
        except Exception as e:
            return False, str(e)


# ============================================================
# КЛУБ: парсинг и пожертвование
# ============================================================
def parse_club_boost(api, club_slug):
    result = {
        "card_id": None,
        "card_image": "",
        "donated": 0,
        "needed": 0,
        "has_card": False,
        "is_locked": False,  # ✅ ПО УМОЛЧАНИЮ СЧИТАЕМ КАРТУ ОТКРЫТОЙ!
    }

    url = f"https://mangabuff.ru/clubs/{club_slug}/boost"
    resp = api._get(url)
    if resp.status_code != 200:
        return result

    html = resp.text

    # --- Парсинг основных данных ---
    match = re.search(r'href="/cards/(\d+)/users"', html)
    if match:
        result["card_id"] = match.group(1)

    match = re.search(r'club-boost__image[^>]*>\s*<img src="([^"]+)"', html)
    if match:
        result["card_image"] = match.group(1)

    match = re.search(
        r"club-boost__change[^>]*>.*?<span>(\d+)</span>\s*/\s*(\d+)", html, re.S
    )
    if match:
        result["donated"] = int(match.group(1))
        result["needed"] = int(match.group(2))

    result["has_card"] = "У вас нет этой карты" not in html

    # --- 🔒 ПРОВЕРКА НА ЗАЛОЧЕННОСТЬ ---
    # По умолчанию: карта ОТКРЫТА (is_locked = False)
    # Меняем на True ТОЛЬКО если найдём явные признаки блокировки

    # Признаки ЗАБЛОКИРОВАННОЙ карты:
    if re.search(r'<i\s+class="[^"]*icon\s+icon-lock[^"]*"', html):
        result["is_locked"] = True
    else:
        result["is_locked"] = False

    # ✅ Для отладки: раскомментируй строку ниже, чтобы видеть статус в консоли
    print(
        f"[DEBUG] card_id={result['card_id']}, has_card={result['has_card']}, is_locked={result['is_locked']}"
    )

    return result


def donate_card_to_club(api, club_slug):
    result = {"success": False, "error": ""}
    try:
        boost_url = f"https://mangabuff.ru/clubs/{club_slug}/boost"
        resp = api._get(boost_url, referer=f"https://mangabuff.ru/clubs/{club_slug}")
        if resp.status_code != 200:
            result["error"] = f"HTTP {resp.status_code}"
            return result

        time.sleep(0.5)

        resp = api._post("https://mangabuff.ru/clubs/boost", data={}, referer=boost_url)

        if resp.status_code == 302:
            result["success"] = True
            return result

        if resp.status_code == 200:
            try:
                jr = resp.json()
                msg = str(jr.get("message", "")).lower()
                if "вклад" in msg or "внесли" in msg or "так держать" in msg:
                    result["success"] = True
                    print(f"  [donate] ✅ {jr.get('message')}")
                    return result
                if jr.get("success"):
                    result["success"] = True
                    return result
                result["error"] = str(jr.get("error") or jr.get("message", ""))[:100]
            except:
                progress = re.search(r"(\d+)\s*/\s*(\d+)", resp.text[:5000])
                if progress:
                    result["success"] = True
                    return result

        if not result["error"]:
            result["error"] = f"HTTP {resp.status_code}"
    except Exception as e:
        result["error"] = str(e)[:80]
        print(f"  [donate] ❌ {e}")
    return result


def get_card_name(api, card_id):
    try:
        resp = api._get(f"https://mangabuff.ru/cards/{card_id}/users")
        if resp.status_code != 200:
            return "?"
        title = re.search(r"<title>([^<]+)</title>", resp.text)
        if title:
            name = re.sub(r"\s*[-|].*$", "", title.group(1).strip())
            name = re.sub(r"^Пользователи с картой\s*", "", name)
            name = re.sub(r"^Карта\s*", "", name)
            return name.strip() or "?"
    except:
        pass
    return "?"


# ============================================================
# АВТОЧЕК
# ============================================================
check_running = {}  # {account_name: bool}
check_stop_events = {}  # {account_name: threading.Event()}


def autocheck_loop(chat_id, club_slug, account_data, interval=30):
    global check_running
    acc_name = account_data.get("name", "unknown")
    check_running[acc_name] = True

    # Создаём отдельное событие остановки для этого аккаунта
    if acc_name not in check_stop_events:
        check_stop_events[acc_name] = threading.Event()
    check_stop = check_stop_events[acc_name]
    check_stop.clear()

    print(f"\n[CHECK] Запуск: {acc_name}, клуб={club_slug}, интервал={interval}с")
    api = MangaBuffAPI(account_data)
    ok, user_id = api.check_auth()
    if not ok:
        print(f"[CHECK] ❌ Не авторизован: {user_id}")
        bot.send_message(chat_id, f"❌ Не авторизован: {user_id}\nАккаунт: {acc_name}")
        check_running[acc_name] = False
        return

    print(f"[CHECK] ✅ Авторизован: {acc_name} (user_id={user_id})")
    bot.send_message(
        chat_id,
        f"✅ Авточек запущен\n👤 {acc_name}\n🏠 {club_slug}\n⏱ Каждые {interval}с",
    )

    total_donated = 0
    cycle = 0
    last_card_id = None
    last_card_name = ""
    errors_in_row = 0
    last_tg_msg_time = 0
    
    while not check_stop.is_set() and check_running.get(acc_name, False):
        cycle += 1
        try:
            club_info = parse_club_boost(api, club_slug)
            if not club_info["card_id"]:
                errors_in_row += 1
                if errors_in_row <= 3 or errors_in_row % 20 == 0:
                    print(f"[CHECK] #{cycle} ❌ {acc_name}: Карта не найдена (ошибок: {errors_in_row})")
                check_stop.wait(interval)
                continue
            
            errors_in_row = 0
            card_id = club_info["card_id"]
            progress = f"{club_info['donated']}/{club_info['needed']}"
            
            if card_id != last_card_id:
                last_card_name = get_card_name(api, card_id)
                last_card_id = card_id
            
            if club_info["has_card"]:
                if club_info.get("is_locked", False):
                    print(f"[CHECK] #{cycle} ⏸ {acc_name}: Карта залочена, пропускаем...")
                    check_stop.wait(interval)
                    continue
                
                print(f"[CHECK] #{cycle} ✅ {acc_name}: Карта есть! Жертвуем...")
                result = donate_card_to_club(api, club_slug)
                if result["success"]:
                    total_donated += 1
                    print(f"[CHECK] #{cycle} 🎁 {acc_name}: Пожертвовано {last_card_name} (всего: {total_donated})")
                    _safe_send(
                        chat_id,
                        f"🎁 {acc_name} пожертвовал: {last_card_name}\n📊 {progress} | Всего: {total_donated}",
                        last_tg_msg_time,
                    )
                    last_tg_msg_time = time.time()
                else:
                    print(f"[CHECK] #{cycle} ❌ {acc_name}: Donate ошибка: {result['error']}")
                check_stop.wait(5)
            else:
                if cycle == 1 or cycle % 60 == 0:
                    print(f"[CHECK] #{cycle} ⏳ {acc_name}: {last_card_name} ({progress})")
                check_stop.wait(interval)
                
        except Exception as e:
            errors_in_row += 1
            if errors_in_row <= 3 or errors_in_row % 20 == 0:
                print(f"[CHECK] #{cycle} ❌ {acc_name}: {e}")
            wait_time = min(interval * (1 + errors_in_row // 5), 300)
            check_stop.wait(wait_time)
    
    check_running[acc_name] = False
    print(f"[CHECK] ⏹ {acc_name} остановлен. Пожертвовано: {total_donated}")
    try:
        bot.send_message(chat_id, f"⏹ {acc_name} остановлен\n🎁 Пожертвовано: {total_donated}")
    except:
        pass


def _safe_send(chat_id, text, last_time, min_gap=2):
    """Отправляет сообщение с rate limit защитой"""
    now = time.time()
    if now - last_time < min_gap:
        time.sleep(min_gap - (now - last_time))
    try:
        bot.send_message(chat_id, text)
    except Exception as e:
        print(f"[TG] ❌ {e}")


# ============================================================
# БОТ
# ============================================================
load_config()


class BotExceptionHandler(telebot.ExceptionHandler):
    def handle(self, exception):
        print(f"\n❌ [BOT ERROR] {exception}")
        traceback.print_exc()
        return True


bot = telebot.TeleBot(
    config.get("bot_token", BOT_TOKEN), exception_handler=BotExceptionHandler()
)


def get_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("🔍 Авточек"),
        types.KeyboardButton("🚀 Все аккаунты"),  # НОВАЯ
    )
    markup.add(
        types.KeyboardButton("⏹ Стоп"),
        types.KeyboardButton("📊 Статус"),
    )
    markup.add(types.KeyboardButton("👥 Аккаунты"))
    return markup


def _get_account():
    accounts = load_accounts()
    club_name = config.get("club_account_name", "")
    if club_name:
        for a in accounts:
            if a.get("name", "").lower() == club_name.lower():
                return a
    valid = [a for a in accounts if a.get("status") == "valid"]
    if valid:
        return valid[0]
    if accounts:
        return accounts[0]
    return None


# --- Команды ---


@bot.message_handler(commands=["start"])
def cmd_start(message):
    bot.send_message(
        message.chat.id,
        "🤖 MangaBuff Club AutoCheck\n\n"
        "🔍 Авточек — запустить проверку клуба\n"
        "⏹ Стоп — остановить\n"
        "👥 Аккаунты — управление\n"
        "📊 Статус — текущий статус\n\n"
        "Настройки:\n"
        "/setclub slug — клуб\n"
        "/setinterval N — интервал (сек)\n"
        "/addacc email password host:port:user:pass — добавить аккаунт\n"
        "/setproxy имя host:port:user:pass — сменить прокси\n"
        "/delacc имя — удалить аккаунт",
        reply_markup=get_keyboard(),
    )


@bot.message_handler(commands=["setclub"])
def cmd_setclub(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.send_message(
            message.chat.id, "❌ Использование: /setclub sumerechniy-rassvet"
        )
        return
    config["club_slug"] = parts[1].strip()
    save_config()
    bot.send_message(message.chat.id, f"✅ Клуб: {config['club_slug']}")


@bot.message_handler(commands=["setinterval"])
def cmd_setinterval(message):
    parts = message.text.split()
    if len(parts) < 2:
        bot.send_message(message.chat.id, "❌ Использование: /setinterval 30")
        return
    try:
        val = int(parts[1])
        if val < 10:
            val = 10
        config["check_interval"] = val
        save_config()
        bot.send_message(message.chat.id, f"✅ Интервал: {val}с")
    except:
        bot.send_message(message.chat.id, "❌ Число!")


@bot.message_handler(commands=["addacc"])
def cmd_addacc(message):
    """Добавляет аккаунт: /addacc email password [proxy]"""
    chat_id = message.chat.id
    parts = message.text.split(maxsplit=3)
    if len(parts) < 3:
        bot.send_message(
            chat_id,
            "📝 `/addacc email password host:port:user:pass`",
        )
        return

    email = parts[1]
    password = parts[2]
    proxy_str = parts[3] if len(parts) > 3 else config.get("default_proxy", "")

    proxy_host, proxy_port, proxy_user, proxy_pass = "", "", "", ""
    if proxy_str:
        pp = proxy_str.split(":")
        if len(pp) >= 2:
            proxy_host, proxy_port = pp[0], pp[1]
        if len(pp) >= 4:
            proxy_user, proxy_pass = pp[2], pp[3]

    proxy_info = f"{proxy_host}:{proxy_port}" if proxy_host else "без прокси"
    bot.send_message(chat_id, f"🔄 Вхожу: {email}\n🌐 Прокси: {proxy_info}")

    temp_acc = {
        "name": email.split("@")[0],
        "proxy_host": proxy_host,
        "proxy_port": proxy_port,
        "proxy_user": proxy_user,
        "proxy_pass": proxy_pass,
        "cookies": [],
    }
    api = MangaBuffAPI(temp_acc)
    success, result = api.login(email, password)

    if success:
        import hashlib

        uid = result["user_id"]
        acc_name = email.split("@")[0]
        new_acc = {
            "id": hashlib.md5(f"{email}{time.time()}".encode()).hexdigest()[:8],
            "name": acc_name,
            "email": email,
            "proxy_host": proxy_host,
            "proxy_port": int(proxy_port) if proxy_port.isdigit() else 0,
            "proxy_user": proxy_user,
            "proxy_pass": proxy_pass,
            "cookies": result["cookies"],
            "status": "valid",
            "user_id": uid,
        }
        accounts = load_accounts()
        # Удаляем старый с таким email/именем
        accounts = [
            a for a in accounts if a.get("name") != acc_name and a.get("email") != email
        ]
        accounts.append(new_acc)
        save_accounts(accounts)

        # Обновляем club_account_name на последний добавленный
        config["club_account_name"] = acc_name
        save_config()

        bot.send_message(
            chat_id,
            f"✅ Аккаунт **{acc_name}** добавлен!\n👤 user_id: {uid}",
        )
    else:
        bot.send_message(chat_id, f"❌ Ошибка входа: {result}")


@bot.message_handler(commands=["setproxy"])
def cmd_setproxy(message):
    parts = message.text.split()
    if len(parts) < 3:
        bot.send_message(message.chat.id, "❌ /setproxy имя host:port:user:pass")
        return
    name = parts[1]
    proxy_parts = parts[2].split(":")

    accounts = load_accounts()
    for a in accounts:
        if a.get("name") == name:
            a["proxy_host"] = proxy_parts[0] if len(proxy_parts) > 0 else ""
            a["proxy_port"] = proxy_parts[1] if len(proxy_parts) > 1 else ""
            a["proxy_user"] = proxy_parts[2] if len(proxy_parts) > 2 else ""
            a["proxy_pass"] = proxy_parts[3] if len(proxy_parts) > 3 else ""
            save_accounts(accounts)
            bot.send_message(message.chat.id, f"✅ Прокси для {name} обновлён")
            return
    bot.send_message(message.chat.id, f"❌ Аккаунт {name} не найден")


@bot.message_handler(commands=["delacc"])
def cmd_delacc(message):
    parts = message.text.split()
    if len(parts) < 2:
        bot.send_message(message.chat.id, "❌ /delacc имя")
        return
    name = parts[1]
    accounts = load_accounts()
    before = len(accounts)
    accounts = [a for a in accounts if a.get("name") != name]
    if len(accounts) < before:
        save_accounts(accounts)
        bot.send_message(message.chat.id, f"✅ {name} удалён")
    else:
        bot.send_message(message.chat.id, f"❌ {name} не найден")


@bot.message_handler(
    func=lambda m: m.text
    and m.text in ["🔍 Авточек", "⏹ Стоп", "👥 Аккаунты", "📊 Статус", "🚀 Все аккаунты"]
)
def handle_buttons(message):
    text = message.text
    chat_id = message.chat.id
    print(f"[BTN] {text} от {chat_id}")
    
    if text == "🔍 Авточек":
        club_slug = config.get("club_slug", "")
        if not club_slug:
            bot.send_message(chat_id, "❌ Клуб не настроен! /setclub slug")
            return
        
        acc = _get_account()
        if not acc:
            bot.send_message(chat_id, "❌ Нет аккаунтов! /addacc")
            return
        
        acc_name = acc.get("name", "unknown")
        if check_running.get(acc_name, False):
            bot.send_message(chat_id, f"⚠️ Аккаунт {acc_name} уже запущен!")
            return
        
        interval = config.get("check_interval", 30)
        check_stop_events[acc_name] = threading.Event()
        threading.Thread(
            target=autocheck_loop,
            args=(chat_id, club_slug, acc, interval),
            daemon=True
        ).start()
        
    elif text == "🚀 Все аккаунты":  # НОВАЯ КНОПКА
        club_slug = config.get("club_slug", "")
        if not club_slug:
            bot.send_message(chat_id, "❌ Клуб не настроен! /setclub slug")
            return
        
        accounts = load_accounts()
        if not accounts:
            bot.send_message(chat_id, "❌ Нет аккаунтов! /addacc")
            return
        
        interval = config.get("check_interval", 30)
        started = 0
        for acc in accounts:
            acc_name = acc.get("name", "unknown")
            if acc.get("status") != "valid":
                continue
            if check_running.get(acc_name, False):
                continue
            check_stop_events[acc_name] = threading.Event()
            threading.Thread(
                target=autocheck_loop,
                args=(chat_id, club_slug, acc, interval),
                daemon=True
            ).start()
            started += 1
        
        bot.send_message(chat_id, f"✅ Запущено {started} аккаунтов параллельно")
        
    elif text == "⏹ Стоп":
        stopped = 0
        for acc_name in list(check_running.keys()):
            if check_running.get(acc_name, False):
                if acc_name in check_stop_events:
                    check_stop_events[acc_name].set()
                check_running[acc_name] = False
                stopped += 1
        if stopped > 0:
            bot.send_message(chat_id, f"⏹ Остановлено {stopped} аккаунтов")
        else:
            bot.send_message(chat_id, "ℹ️ Авточек не запущен")
    
    elif text == "👥 Аккаунты":
        accounts = load_accounts()
        if not accounts:
            bot.send_message(chat_id, "📋 Нет аккаунтов\n/addacc имя {cookies}")
            return
        lines = []
        for a in accounts:
            proxy = f"{a.get('proxy_host','')}:{a.get('proxy_port','')}" if a.get('proxy_host') else "нет"
            status = "🟢" if check_running.get(a.get('name'), False) else "🔴"
            lines.append(f"{status} {a.get('name','?')} ({a.get('status','?')}) proxy={proxy}")
        bot.send_message(chat_id, "👥 Аккаунты:\n" + "\n".join(lines))
    
    elif text == "📊 Статус":
        club_slug = config.get("club_slug", "")
        interval = config.get("check_interval", 30)
        running_count = sum(1 for v in check_running.values() if v)
        status = f"🟢 Запущено {running_count} аккаунтов" if running_count > 0 else "🔴 Остановлен"
        bot.send_message(
            chat_id,
            f"📊 Статус\n{status}\n🏠 Клуб: {club_slug or 'не задан'}\n⏱ Интервал: {interval}с",
        )


# ============================================================
# ЗАПУСК
# ============================================================
if __name__ == "__main__":
    print("🤖 MangaBuff Club AutoCheck Bot")
    print("=" * 40)

    accounts = load_accounts()
    print(f"📁 Accounts: {ACCOUNTS_FILE} (exists: {ACCOUNTS_FILE.exists()})")
    print(f"👥 Аккаунтов: {len(accounts)}")
    print(f"🏠 Клуб: {config.get('club_slug', 'не задан')}")
    print(f"⏱ Интервал: {config.get('check_interval', 30)}с")
    print()

    token = config.get("bot_token", BOT_TOKEN)
    if not token:
        print("❌ Не указан BOT_TOKEN!")
        print("Укажи его в config_check.json или в переменной BOT_TOKEN в коде")
        sys.exit(1)

    print("✅ Бот запущен!")
    print("Ctrl+C для остановки")
    print()

    try:
        bot.infinity_polling(timeout=30, long_polling_timeout=30)
    except KeyboardInterrupt:
        print("\n⏹ Остановлен")
        check_stop.set()

# button button--primary club__boost-btn
# icon icon-lock
