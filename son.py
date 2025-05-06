from colorama import init, Fore, Style
import time
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageEnhance, ImageOps, ImageFilter
import pytesseract
from io import BytesIO
import re
import json
import os
import random
import schedule
from datetime import datetime, timedelta
import threading

pytesseract.pytesseract.tesseract_cmd = '/data/data/com.termux/files/usr/bin/tesseract'

init(autoreset=True)

# Üstyazı ve banner
print(Fore.YELLOW + Style.BRIGHT + "by KozmoPoliT7".center(50, "-"))
banner_lines = [
    r"         __  __      __                          ",
    r"         \ \/ /___  / /_  ______  __  __         ",
    r"          \  / __ \/ / / / / __ \/ / / /         ",
    r"          / / /_/ / / /_/ / / / / /_/ /          ",
    r"__  __   /_/\____/_/\__,_/_/ /_/\__,_/           ",
    r"\ \/ /___  _________/ /___ _____ ___  __ ___  __ ",
    r" \  / __ \/ ___/ __  / __ `/ __ `__ \/ / __ \/ / ",
    r" / / /_/ / /  / /_/ / /_/ / / / / / / / / / / /  ",
    r"/_/\____/_/   \__,_/\__,_/_/ /_/ /_/_/_/ /_/_/   ",
    r"                 _    _____ ___                  ",
    r"                | |  / <  /<  /                  ",
    r"                | | / // / / /                   ",
    r"                | |/ // / / /                    ",
    r"                |___//_(_)_/                     ",
    r"                                                 "
]
for line in banner_lines:
    print(Fore.MAGENTA + Style.BRIGHT + line)
    time.sleep(0.08)
print(Fore.YELLOW + Style.BRIGHT + "by KozmoPoliT7".center(50, "-"))

# Kat bazında koltuk numaraları
KAT_KOLTUKLARI = {
    "82": [str(i) for i in range(1, 149)],  # Zemin Kat: 1-148
    "80": [str(i) for i in range(1, 96)],   # 1. Kat: 1-95
    "81": [str(i) for i in range(1, 141)]   # Bodrum Kat: 1-140
}

# JSON dosya konumu
PROFILE_FILE = "profiles.json"

def load_profiles():
    if os.path.exists(PROFILE_FILE):
        with open(PROFILE_FILE, "r", encoding="utf-8") as f:
            try:
                profiles = json.load(f)
                for profile in profiles:
                    if "abonelik" not in profile:
                        profile["abonelik"] = []
                return profiles
            except json.JSONDecodeError:
                print(Fore.RED + "⚠️ Profiller yüklenemedi, JSON formatı hatalı!")
                return []
    return []

def save_profiles(data):
    with open(PROFILE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def choose_profile():
    profiles = load_profiles()
    if not profiles:
        print(Fore.RED + "⚠️ Kayıtlı profil bulunamıyor.")
        return None
    
    print(Fore.CYAN + "\n📂 Kayıtlı Profiller:")
    for i, profile in enumerate(profiles, 1):
        display_name = profile.get("name", profile["username"])
        print(f"{i}. {display_name}")
    
    try:
        secim = int(input(Fore.CYAN + "Seçiminiz (1-{}): ".format(len(profiles))))
        if 1 <= secim <= len(profiles):
            return profiles[secim - 1]
        else:
            print(Fore.RED + "⚠️ Geçersiz seçim.")
            return None
    except ValueError:
        print(Fore.RED + "⚠️ Geçersiz giriş, lütfen bir sayı girin.")
        return None

def start_session():
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10)",
        "Accept-Language": "tr-TR,tr;q=0.9",
    }
    return session, headers

def get_php_sessid(session, headers):
    url = "https://kutuphane.umraniye.bel.tr/yordam/"
    response = session.get(url, headers=headers)
    cookies = session.cookies.get_dict()
    return cookies.get("PHPSESSID", None)

def get_token(session, headers):
    giris_url = "https://kutuphane.umraniye.bel.tr/rezervasyon/?p=2&dil=0&islem=giris"
    r = session.get(giris_url, headers=headers)
    soup = BeautifulSoup(r.text, "html.parser")
    token = soup.find("input", {"name": "token"})["value"]
    return token, giris_url

def get_captcha_image(session, headers):
    captcha_url = "https://kutuphane.umraniye.bel.tr/rezervasyon/inc/captcha.php?form=girisForm"
    captcha_resp = session.get(captcha_url, headers=headers)
    img = Image.open(BytesIO(captcha_resp.content))
    img = img.resize((img.width * 3, img.height * 3), Image.Resampling.LANCZOS)
    img = ImageOps.invert(img.convert("L"))
    img = ImageEnhance.Sharpness(img).enhance(2.5)
    img = ImageEnhance.Contrast(img).enhance(3.0)
    return img

def solve_captcha(img):
    captcha_code = pytesseract.image_to_string(
        img,
        lang="eng",
        config="--psm 8 -c tessedit_char_whitelist=0123456789"
    ).strip()
    return captcha_code

def login_user(session, headers, token, giris_url, username, password):
    login_url = "https://kutuphane.umraniye.bel.tr/rezervasyon/inc/form.inc.php"
    attempt = 0
    while True:
        attempt += 1
        img = get_captcha_image(session, headers)
        captcha_code = solve_captcha(img)
        if not (len(captcha_code) == 6 and captcha_code.isdigit()):
            print(Fore.YELLOW + f"↺ {attempt}. deneme - Geçersiz CAPTCHA: {captcha_code}")
            time.sleep(1)
            continue
        print(Fore.GREEN + f"✓ CAPTCHA çözümü denemesi ({attempt}. deneme): {captcha_code}")
        payload = {
            "dil": "0",
            "islem": "giris",
            "token": token,
            "kullanici": username,
            "sifre": password,
            "code_girisForm": captcha_code,
        }
        login_headers = headers.copy()
        login_headers.update({
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Referer": giris_url,
            "Origin": "https://kutuphane.umraniye.bel.tr",
            "X-Requested-With": "XMLHttpRequest",
            "token": token,
        })
        response = session.post(login_url, data=payload, headers=login_headers)
        if "Giriş işlemi başarılı" in response.text:
            print(Fore.GREEN + f"✅ Giriş başarılı ({username})")
            return True
        elif "Hatalı kod yazımı." in response.text:
            print(Fore.RED + "❌ CAPTCHA hatalı. Tekrar deneniyor...")
            time.sleep(1)
        elif "Hatalı Şifre." in response.text:
            print(Fore.RED + f"⚠️ Giriş başarısız ({username}) - Hatalı kullanıcı adı veya şifre!")
            return False
        else:
            print(Fore.RED + "⚠️ Giriş başarısız - Bilinmeyen hata.")
            print(response.text)
            return False

def get_reservation_tokens(session, headers):
    reservation_page_url = "https://kutuphane.umraniye.bel.tr/rezervasyon/?p=1&dil=0"
    response = session.get(reservation_page_url, headers=headers)
    html = response.text
    def extract_token_direct(source, keyword):
        pattern = rf'{keyword}.*?token:\s*"([a-fA-F0-9]+)"'
        match = re.search(pattern, source, re.DOTALL)
        return match.group(1) if match else None
    def extract_onay_token(source):
        soup = BeautifulSoup(source, "html.parser")
        forms = soup.find_all("form", {"action": "inc/form.inc.php"})
        for form in forms:
            if form.find("input", {"name": "islem", "value": "rezervasyonMetinOnay"}):
                token_input = form.find("input", {"name": "token"})
                if token_input:
                    return token_input.get("value")
        return None
    getir_token = extract_token_direct(html, "salonRezervasyonGetir")
    yap_token = extract_token_direct(html, "rezervasyonYap")
    onay_token = extract_onay_token(html)
    print(Fore.CYAN + f"📌 GetirToken: {getir_token}")
    print(Fore.CYAN + f"📌 YapToken: {yap_token}")
    print(Fore.CYAN + f"📌 OnayToken: {onay_token if onay_token else 'YOK'}")
    return getir_token, yap_token, onay_token, reservation_page_url

def check_empty_seats(session, headers, reservation_page_url, getir_token, secilen_tarih, kat_kodu, seans_kodu):
    seans_map = {
        "1": "08:30 - 13:50",
        "2": "14:00 - 19:50",
        "3": "20:00 - 23:50"
    }
    seans_saat = seans_map.get(seans_kodu, "14:00 - 19:50")
    rezervasyon_post_url = "https://kutuphane.umraniye.bel.tr/rezervasyon/inc/form.inc.php"
    rezervasyon_payload = {
        "islem": "salonRezervasyonGetir",
        "salon": kat_kodu,
        "seans": seans_saat,
        "tarih": secilen_tarih,
        "token": getir_token,
    }
    rezervasyon_headers = headers.copy()
    rezervasyon_headers.update({
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://kutuphane.umraniye.bel.tr",
        "Referer": reservation_page_url,
        "X-Requested-With": "XMLHttpRequest",
        "token": getir_token,
    })
    response_rez = session.post(rezervasyon_post_url, data=rezervasyon_payload, headers=rezervasyon_headers)
    response_text = response_rez.text
    try:
        response_dict = json.loads(response_text)
    except json.JSONDecodeError:
        print(Fore.RED + "⚠️ Boş koltuk verisi alınamadı. JSON çözümlemesi başarısız.")
        print(Fore.YELLOW + f"Yanıt: {response_text}")
        return []
    empty_seats = []
    if isinstance(response_dict, list):
        for seat in response_dict:
            if isinstance(seat, str) and '-' in seat:
                seat_number = seat.split('-')[1]
                empty_seats.append(seat_number)
    elif isinstance(response_dict, dict):
        for seat in response_dict.values():
            if isinstance(seat, str) and '-' in seat:
                seat_number = seat.split('-')[1]
                empty_seats.append(seat_number)
    return empty_seats

def make_reservation(session, headers, yap_token, user, reservation_page_url):
    seans_kodu = user["seans"]
    kat_kodu = user["kat"]
    secilen_koltuk = user["masa"]
    secilen_tarih = user.get("tarih", (datetime.today() + timedelta(days=2)).strftime("%Y-%m-%d"))
    seans_map = {
        "1": "08:30 - 13:50",
        "2": "14:00 - 19:50",
        "3": "20:00 - 23:50"
    }
    seans_saat = seans_map.get(seans_kodu, "14:00 - 19:50")
    rezervasyonyap_post_url = "https://kutuphane.umraniye.bel.tr/rezervasyon/inc/form.inc.php"
    rezervasyonyap_payload = {
        "islem": "rezervasyonYap",
        "kime": "",
        "seans": seans_saat,
        "tarih": secilen_tarih,
        "secim": kat_kodu + "-" + secilen_koltuk,
        "token": yap_token,
    }
    rezervasyonyap_headers = headers.copy()
    rezervasyonyap_headers.update({
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://kutuphane.umraniye.bel.tr",
        "Referer": reservation_page_url,
        "X-Requested-With": "XMLHttpRequest",
        "token": yap_token,
    })
    try:
        response = session.post(rezervasyonyap_post_url, data=rezervasyonyap_payload, headers=rezervasyonyap_headers)
        response.raise_for_status()  # HTTP hata kodlarını kontrol et
        return response
    except requests.exceptions.RequestException as e:
        print(f"⚠️ Rezervasyon isteği başarısız: {str(e)}")
        return None
        
from flask import request, flash
# ... (diğer mevcut import’lar: json, os, requests, BeautifulSoup, PIL, pytesseract, datetime, timedelta, KAT_KOLTUKLARI)

from flask import request, flash
# ... (diğer mevcut import’lar: json, os, requests, BeautifulSoup, PIL, pytesseract, datetime, timedelta, KAT_KOLTUKLARI)

from flask import request, flash
# ... (diğer mevcut import’lar: json, os, datetime, KAT_KOLTUKLARI)

def create_subscription(username, profiles):
    profile = next((p for p in profiles if p["username"] == username), {})
    if not profile:
        print(f"⚠️ create_subscription: Profil bulunamadı ({username})")
        return {"error": "Profil bulunamadı!"}

    if request.method == 'POST':
        kat_kodu = request.form.get('kat')
        seans_kodu = request.form.get('seans')
        koltuk_index = request.form.get('koltuk')

        if not all([kat_kodu, seans_kodu, koltuk_index]):
            print(f"⚠️ create_subscription: Kat, seans veya koltuk seçimi eksik ({username})")
            return {"error": "Kat, seans veya koltuk seçimi eksik!"}

        # Koltuk listesi
        koltuklar = KAT_KOLTUKLARI.get(kat_kodu, [])
        if not koltuklar:
            print(f"⚠️ create_subscription: Geçersiz kat seçimi ({username}, kat: {kat_kodu})")
            return {"error": "Geçersiz kat seçimi!"}

        try:
            koltuk_index = int(koltuk_index) - 1
            if not (0 <= koltuk_index < len(koltuklar)):
                print(f"⚠️ create_subscription: Geçersiz koltuk seçimi ({username}, index: {koltuk_index})")
                return {"error": "Geçersiz koltuk seçimi!"}
            koltuk = koltuklar[koltuk_index]
        except ValueError:
            print(f"⚠️ create_subscription: Koltuk seçimi bir sayı olmalı ({username}, input: {koltuk_index})")
            return {"error": "Koltuk seçimi bir sayı olmalı!"}

        # Mevcut abonelikleri kontrol et
        abone_koltuklar = {}
        seans_map = {"1": "Sabah", "2": "Öğle", "3": "Akşam"}
        for p in profiles:
            for abonelik in p.get("abonelik", []):
                if abonelik.get("aktif", False) and abonelik["kat"] == kat_kodu:
                    koltuk_no = abonelik["koltuk"]
                    seans = abonelik["seans_kodu"]
                    if koltuk_no not in abone_koltuklar:
                        abone_koltuklar[koltuk_no] = []
                    abone_koltuklar[koltuk_no].append({
                        "name": p.get("name", p["username"]),
                        "seans": seans_map.get(seans, "Bilinmeyen")
                    })

        # Koltuk dolu mu kontrol et
        if koltuk in abone_koltuklar and any(abone["seans"] == seans_map.get(seans_kodu) for abone in abone_koltuklar[koltuk]):
            print(f"⚠️ create_subscription: Koltuk {koltuk} zaten {seans_map.get(seans_kodu)} seansı için dolu ({username})")
            return {"error": f"Koltuk {koltuk} zaten {seans_map.get(seans_kodu)} seansı için dolu!"}

        # Abonelik ekle
        if "abonelik" not in profile:
            profile["abonelik"] = []
        profile["abonelik"].append({
            "aktif": True,
            "kat": kat_kodu,
            "seans_kodu": seans_kodu,
            "koltuk": koltuk
        })
        save_profiles(profiles)
        print(f"✅ create_subscription: Abonelik oluşturuldu ({username}, kat: {kat_kodu}, seans: {seans_kodu}, koltuk: {koltuk})")
        return {"success": "Abonelik oluşturuldu!"}

    # GET isteği için koltuk listesini hazırla
    kat_kodu = request.args.get('kat', '82')
    seans_kodu = request.args.get('seans', '2')
    koltuklar = KAT_KOLTUKLARI.get(kat_kodu, [])
    abone_koltuklar = {}
    seans_map = {"1": "Sabah", "2": "Öğle", "3": "Akşam"}
    for p in profiles:
        for abonelik in p.get("abonelik", []):
            if abonelik.get("aktif", False) and abonelik["kat"] == kat_kodu:
                koltuk_no = abonelik["koltuk"]
                seans = abonelik["seans_kodu"]
                if koltuk_no not in abone_koltuklar:
                    abone_koltuklar[koltuk_no] = []
                abone_koltuklar[koltuk_no].append({
                    "name": p.get("name", p["username"]),
                    "seans": seans_map.get(seans, "Bilinmeyen")
                })

    koltuk_listesi = [
        {"koltuk": k, "dolu": k in abone_koltuklar, "abone": abone_koltuklar.get(k, [])} 
        for k in koltuklar
    ]
    return {
        "koltuklar": koltuk_listesi,
        "kat": kat_kodu,
        "seans": seans_kodu,
        "username": username
    }

def cancel_subscription(username, profiles):
    profile = next((p for p in profiles if p["username"] == username), {})
    abonelikler = profile.get("abonelik", [])
    
    if not abonelikler:
        print(f"⚠️ cancel_subscription: Abonelik bulunamıyor ({username})")
        return {"error": "Abonelik bulunamıyor.", "abonelikler": []}

    if request.method == 'POST':
        try:
            secim = int(request.form.get('abonelik_index')) - 1
            if 0 <= secim < len(abonelikler):
                abonelikler[secim]["aktif"] = False
                save_profiles(profiles)
                print(f"✅ cancel_subscription: Abonelik iptal edildi ({username}, index: {secim})")
                return {"success": "Abonelik iptal edildi.", "abonelikler": [
                    {
                        "kat": abonelik["kat"],
                        "seans": {"1": "Sabah", "2": "Öğle", "3": "Akşam"}.get(abonelik["seans_kodu"], "Bilinmeyen"),
                        "koltuk": abonelik["koltuk"],
                        "aktif": abonelik.get("aktif", False)
                    }
                    for abonelik in abonelikler
                ]}
            else:
                print(f"⚠️ cancel_subscription: Geçersiz abonelik seçimi ({username}, index: {secim})")
                return {"error": "Geçersiz abonelik seçimi.", "abonelikler": []}
        except (ValueError, TypeError):
            print(f"⚠️ cancel_subscription: Geçersiz giriş, lütfen bir sayı seçin ({username})")
            return {"error": "Geçersiz giriş, lütfen bir sayı seçin.", "abonelikler": []}

    return {"abonelikler": [
        {
            "kat": abonelik["kat"],
            "seans": {"1": "Sabah", "2": "Öğle", "3": "Akşam"}.get(abonelik["seans_kodu"], "Bilinmeyen"),
            "koltuk": abonelik["koltuk"],
            "aktif": abonelik.get("aktif", False)
        }
        for abonelik in abonelikler
    ], "username": username}

def edit_subscription(username, profiles):
    profile = next((p for p in profiles if p["username"] == username), {})
    abonelikler = profile.get("abonelik", [])
    
    if not abonelikler:
        print(f"⚠️ edit_subscription: Abonelik bulunamıyor ({username})")
        return {"error": "Abonelik bulunamıyor.", "abonelikler": []}

    if request.method == 'POST':
        try:
            secim = int(request.form.get('abonelik_index')) - 1
            if not (0 <= secim < len(abonelikler)):
                print(f"⚠️ edit_subscription: Geçersiz abonelik seçimi ({username}, index: {secim})")
                return {"error": "Geçersiz abonelik seçimi.", "abonelikler": []}
            
            kat_kodu = request.form.get('kat')
            seans_kodu = request.form.get('seans')
            koltuk_index = request.form.get('koltuk')

            if not all([kat_kodu, seans_kodu, koltuk_index]):
                print(f"⚠️ edit_subscription: Kat, seans veya koltuk seçimi eksik ({username})")
                return {"error": "Kat, seans veya koltuk seçimi eksik!", "abonelikler": []}

            koltuklar = KAT_KOLTUKLARI.get(kat_kodu, [])
            if not koltuklar:
                print(f"⚠️ edit_subscription: Geçersiz kat seçimi ({username}, kat: {kat_kodu})")
                return {"error": "Geçersiz kat seçimi!", "abonelikler": []}

            try:
                koltuk_index = int(koltuk_index) - 1
                if not (0 <= koltuk_index < len(koltuklar)):
                    print(f"⚠️ edit_subscription: Geçersiz koltuk seçimi ({username}, index: {koltuk_index})")
                    return {"error": "Geçersiz koltuk seçimi!", "abonelikler": []}
                koltuk = koltuklar[koltuk_index]
            except ValueError:
                print(f"⚠️ edit_subscription: Koltuk seçimi bir sayı olmalı ({username}, input: {koltuk_index})")
                return {"error": "Koltuk seçimi bir sayı olmalı!", "abonelikler": []}

            # Mevcut abonelikleri kontrol et
            abone_koltuklar = {}
            seans_map = {"1": "Sabah", "2": "Öğle", "3": "Akşam"}
            for p in profiles:
                for abonelik in p.get("abonelik", []):
                    if abonelik.get("aktif", False) and abonelik["kat"] == kat_kodu:
                        koltuk_no = abonelik["koltuk"]
                        seans = abonelik["seans_kodu"]
                        if koltuk_no not in abone_koltuklar:
                            abone_koltuklar[koltuk_no] = []
                        abone_koltuklar[koltuk_no].append({
                            "name": p.get("name", p["username"]),
                            "seans": seans_map.get(seans, "Bilinmeyen")
                        })

            # Koltuk dolu mu kontrol et
            if koltuk in abone_koltuklar and any(abone["seans"] == seans_map.get(seans_kodu) for abone in abone_koltuklar[koltuk]):
                print(f"⚠️ edit_subscription: Koltuk {koltuk} zaten {seans_map.get(seans_kodu)} seansı için dolu ({username})")
                return {"error": f"Koltuk {koltuk} zaten {seans_map.get(seans_kodu)} seansı için dolu!", "abonelikler": []}

            # Aboneliği güncelle
            abonelikler[secim] = {
                "aktif": True,
                "kat": kat_kodu,
                "seans_kodu": seans_kodu,
                "koltuk": koltuk
            }
            save_profiles(profiles)
            print(f"✅ edit_subscription: Abonelik düzenlendi ({username}, kat: {kat_kodu}, seans: {seans_kodu}, koltuk: {koltuk})")
            return {"success": "Abonelik düzenlendi.", "abonelikler": [
                {
                    "kat": abonelik["kat"],
                    "seans": {"1": "Sabah", "2": "Öğle", "3": "Akşam"}.get(abonelik["seans_kodu"], "Bilinmeyen"),
                    "koltuk": abonelik["koltuk"],
                    "aktif": abonelik.get("aktif", False)
                }
                for abonelik in abonelikler
            ]}
        except (ValueError, TypeError):
            print(f"⚠️ edit_subscription: Geçersiz giriş, lütfen bir sayı seçin ({username})")
            return {"error": "Geçersiz giriş, lütfen bir sayı seçin.", "abonelikler": []}

    return {"abonelikler": [
        {
            "kat": abonelik["kat"],
            "seans": {"1": "Sabah", "2": "Öğle", "3": "Akşam"}.get(abonelik["seans_kodu"], "Bilinmeyen"),
            "koltuk": abonelik["koltuk"],
            "aktif": abonelik.get("aktif", False)
        }
        for abonelik in abonelikler
    ], "username": username}

def manage_subscription(profile_name, profiles):
    profile = next((p for p in profiles if p["username"] == profile_name), {})
    abonelikler = profile.get("abonelik", [])
    
    while True:
        print(Fore.CYAN + f"\n📅 Abonelik Yönetimi ({profile.get('name', profile['username'])}):")
        if abonelikler:
            print(Fore.GREEN + "Aktif Abonelikler:")
            seans_map = {
                "1": "Sabah",
                "2": "Öğle",
                "3": "Akşam"
            }
            for i, abonelik in enumerate(abonelikler, 1):
                if abonelik.get("aktif", False):
                    print(f"{i}. Kat: {abonelik['kat']}, Seans: {seans_map.get(abonelik['seans_kodu'], 'Bilinmeyen')}, Koltuk: {abonelik['koltuk']}")
        
        print("\nSeçenekler:")
        print("  1. 🆕 Yeni Abonelik Oluştur")
        print("  2. ✍ Abonelik Düzenle")
        print("  3. 🗑 Abonelik İptal Et")
        print("  0. 🔙 Geri Dön")
        
        secim = input(Fore.CYAN + "Seçiminiz (0-3): ").strip()
        
        if secim == "0" or secim == "":
            print(Fore.YELLOW + "🔙 Ana menüye dönülüyor...")
            break
        
        try:
            secim = int(secim)
            if secim not in [1, 2, 3]:
                print(Fore.RED + "⚠️ Geçersiz seçim, lütfen 0-3 arasında bir sayı girin.")
                continue
        except ValueError:
            print(Fore.RED + "⚠️ Geçersiz giriş, lütfen bir sayı girin.")
            continue
        
        if secim == 1:
            create_subscription(profile_name, profiles)
        elif secim == 2:
            edit_subscription(profile_name, profiles)
        elif secim == 3:
            cancel_subscription(profile_name, profiles)
        
        save_profiles(profiles)

def run_daily_reservations():
    profiles = load_profiles()
    for profile in profiles:
        abonelikler = profile.get("abonelik", [])
        if not abonelikler:
            continue
        
        username = profile["username"]
        for abonelik in abonelikler:
            if not abonelik.get("aktif", False):
                continue
            
            kat = abonelik["kat"]
            seans_kodu = abonelik["seans_kodu"]
            koltuk = abonelik["koltuk"]
            tarih = (datetime.today() + timedelta(days=2)).strftime("%Y-%m-%d")
            
            seans_map = {
                "1": "08:30 - 13:50",
                "2": "14:00 - 19:50",
                "3": "20:00 - 23:50"
            }
            seans_saat = seans_map.get(seans_kodu, "14:00 - 19:50")
            
            valid_seans = ["1", "2"] if kat == "80" else ["1", "2", "3"]
            if seans_kodu not in valid_seans:
                print(Fore.RED + f"Hata: {username} için geçersiz seans kodu ({seans_kodu}) kat {kat} ile uyumsuz!")
                continue
            
            print(Fore.CYAN + f"\n⏳ {username} için otomatik rezervasyon başlatılıyor...")
            print(Fore.CYAN + f"Kat: {kat}, Seans: {seans_saat}, Koltuk: {koltuk}, Tarih: {tarih}")
            
            session, headers = start_session()
            PHPSESSID = get_php_sessid(session, headers)
            if not PHPSESSID:
                print(Fore.RED + f"PHPSESSID alınamadı ({username}), geçiliyor...")
                continue
            
            token, giris_url = get_token(session, headers)
            success = login_user(session, headers, token, giris_url, profile["username"], profile["password"])
            
            if success:
                getir_token, yap_token, onay_token, reservation_page_url = get_reservation_tokens(session, headers)
                if getir_token and yap_token:
                    if onay_token:
                        onay_post_url = "https://kutuphane.umraniye.bel.tr/rezervasyon/inc/form.inc.php"
                        onay_payload = {
                            "token": onay_token,
                            "islem": "rezervasyonMetinOnay",
                            "onaydurum": "1"
                        }
                        onay_headers = headers.copy()
                        onay_headers.update({
                            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                            "Origin": "https://kutuphane.umraniye.bel.tr",
                            "Referer": reservation_page_url,
                            "X-Requested-With": "XMLHttpRequest",
                            "token": onay_token,
                        })
                        response_onay = session.post(onay_post_url, data=onay_payload, headers=onay_headers)
                        if "teşekkürler" in response_onay.text.lower():
                            print(Fore.GREEN + "✅ Onay metni başarıyla imzalandı!")
                        else:
                            print(Fore.RED + f"❌ Onay metni imzalanamadı ({username})!")
                            continue
                    
                    user = {
                        "username": profile["username"],
                        "password": profile["password"],
                        "kat": kat,
                        "seans": seans_kodu,
                        "masa": koltuk,
                        "tarih": tarih
                    }
                    make_reservation(session, headers, yap_token, user, reservation_page_url)
                else:
                    print(Fore.RED + f"Tokenler alınamadı ({username}), işlem durduruluyor.")
            else:
                print(Fore.RED + f"Giriş başarısız ({username}), kullanıcı geçiliyor...")
            
            time.sleep(2)

def start_auto_reservation():
    def run_schedule():
        schedule.every().day.at("00:01").do(run_daily_reservations)
        print(Fore.YELLOW + "Otomatik rezervasyon sistemi başlatıldı (Her gün 00:01'de çalışacak)...")
        while True:
            schedule.run_pending()
            time.sleep(60)
    
    thread = threading.Thread(target=run_schedule, daemon=True)
    thread.start()

def wait_for_empty_seat(session, headers, reservation_page_url, getir_token, secilen_tarih, kat_kodu, seans_kodu, wait_time=2, max_attempts=10000):
    for attempt in range(max_attempts):
        try:
            print(Fore.YELLOW + f"Boş koltuk kontrol ediliyor... (Deneme {attempt + 1}/{max_attempts})")
            empty_seats = check_empty_seats(session, headers, reservation_page_url, getir_token, secilen_tarih, kat_kodu, seans_kodu)
            if empty_seats:
                print(Fore.GREEN + f"Boş Koltuklar: {', '.join(empty_seats)}")
                return empty_seats
            else:
                print(Fore.RED + "Bu katta şu anda boş koltuk bulunmamaktadır. Tekrar deneniyor...")
                time.sleep(wait_time)
        except Exception as e:
            print(Fore.RED + f"⚠️ Koltuk kontrolü sırasında hata: {str(e)}")
            return []
    
    print(Fore.RED + "⚠️ Maksimum deneme sayısına ulaşıldı, boş koltuk bulunamadı.")
    return []
    
def choose_random_seat(empty_seats):
    return random.choice(empty_seats)

def main_menu():
    profiles = load_profiles()
    
    start_auto_reservation()  # Otomatik rezervasyon sistemini başlat
    
    while True:
        print(Fore.CYAN + "\n🚪 Ana Menü:")
        print("  1. 🆕 Yeni Giriş Yap")
        print("  2. 🗂️ Kayıtlı Profili Kullan")
        print("  3. 📅 Abonelik Yönetimi")
        print("  0. 🚪 Çıkış")
        
        secim = input(Fore.CYAN + "Seçiminiz (0-3): ").strip()
        
        if secim == "0" or secim == "":
            print(Fore.YELLOW + "👋 Programdan çıkılıyor...")
            break
        
        try:
            secim = int(secim)
            if secim not in [1, 2, 3]:
                print(Fore.RED + "⚠️ Geçersiz seçim, lütfen 0-3 arasında bir sayı girin.")
                continue
        except ValueError:
            print(Fore.RED + "⚠️ Geçersiz giriş, lütfen bir sayı girin.")
            continue
        
        if secim == 1:  # Yeni Giriş Yap
            USERNAME = input(Fore.CYAN + "Kullanıcı Adınızı Girin: ")
            PASSWORD = input(Fore.CYAN + "Şifrenizi Girin: ")
            NAME = input(Fore.CYAN + "Adınızı Girin (örn: Ali İhsan): ").strip()
            kaydet = input(Fore.CYAN + "💾 Bu bilgileri profil olarak kaydetmek ister misiniz? (E/H): ").strip().upper()
            if kaydet == "E":
                profiles.append({
                    "username": USERNAME,
                    "password": PASSWORD,
                    "name": NAME if NAME else USERNAME,
                    "abonelik": []
                })
                save_profiles(profiles)
                print(Fore.GREEN + f"✅ Profil kaydedildi (Ad: {NAME if NAME else USERNAME}).")
            
            session, headers = start_session()
            PHPSESSID = get_php_sessid(session, headers)
            if not PHPSESSID:
                print(Fore.RED + "⚠️ PHPSESSID alınamadı!")
                continue
            
            token, giris_url = get_token(session, headers)
            success = login_user(session, headers, token, giris_url, USERNAME, PASSWORD)
            if success:
                getir_token, yap_token, onay_token, reservation_page_url = get_reservation_tokens(session, headers)
                if getir_token and yap_token:
                    if onay_token:
                        onay_post_url = "https://kutuphane.umraniye.bel.tr/rezervasyon/inc/form.inc.php"
                        onay_payload = {
                            "token": onay_token,
                            "islem": "rezervasyonMetinOnay",
                            "onaydurum": "1"
                        }
                        onay_headers = headers.copy()
                        onay_headers.update({
                            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                            "Origin": "https://kutuphane.umraniye.bel.tr",
                            "Referer": reservation_page_url,
                            "X-Requested-With": "XMLHttpRequest",
                            "token": onay_token,
                        })
                        response_onay = session.post(onay_post_url, data=onay_payload, headers=onay_headers)
                        if "teşekkürler" in response_onay.text.lower():
                            print(Fore.GREEN + "✅ Onay metni başarıyla imzalandı!")
                        else:
                            print(Fore.RED + "❌ Onay metni imzalanamadı!")
                            continue
                    
                    user = {
                        "username": USERNAME,
                        "password": PASSWORD
                    }
                    manual_reservation(session, headers, getir_token, yap_token, reservation_page_url, user)
                else:
                    print(Fore.RED + "⚠️ Tokenler alınamadı!")
            else:
                print(Fore.RED + "⚠️ Giriş başarısız!")
        
        elif secim == 2:  # Kayıtlı Profili Kullan
            profile = choose_profile()
            if not profile:
                continue
            USERNAME = profile["username"]
            PASSWORD = profile["password"]
            
            session, headers = start_session()
            PHPSESSID = get_php_sessid(session, headers)
            if not PHPSESSID:
                print(Fore.RED + "⚠️ PHPSESSID alınamadı!")
                continue
            
            token, giris_url = get_token(session, headers)
            success = login_user(session, headers, token, giris_url, USERNAME, PASSWORD)
            if success:
                getir_token, yap_token, onay_token, reservation_page_url = get_reservation_tokens(session, headers)
                if getir_token and yap_token:
                    if onay_token:
                        onay_post_url = "https://kutuphane.umraniye.bel.tr/rezervasyon/inc/form.inc.php"
                        onay_payload = {
                            "token": onay_token,
                            "islem": "rezervasyonMetinOnay",
                            "onaydurum": "1"
                        }
                        onay_headers = headers.copy()
                        onay_headers.update({
                            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                            "Origin": "https://kutuphane.umraniye.bel.tr",
                            "Referer": reservation_page_url,
                            "X-Requested-With": "XMLHttpRequest",
                            "token": onay_token,
                        })
                        response_onay = session.post(onay_post_url, data=onay_payload, headers=onay_headers)
                        if "teşekkürler" in response_onay.text.lower():
                            print(Fore.GREEN + "✅ Onay metni başarıyla imzalandı!")
                        else:
                            print(Fore.RED + "❌ Onay metni imzalanamadı!")
                            continue
                    
                    user = {
                        "username": USERNAME,
                        "password": PASSWORD
                    }
                    manual_reservation(session, headers, getir_token, yap_token, reservation_page_url, user)
                else:
                    print(Fore.RED + "⚠️ Tokenler alınamadı!")
            else:
                print(Fore.RED + "⚠️ Giriş başarısız!")
        
        elif secim == 3:  # Abonelik Yönetimi
            profile = choose_profile()
            if profile:
                manage_subscription(profile["username"], profiles)

def manual_reservation(session, headers, getir_token, yap_token, reservation_page_url, user):
    bugun = datetime.now()
    yarin = bugun + timedelta(days=1)
    ozel = yarin + timedelta(days=1)
    bugun_str = bugun.strftime("%Y-%m-%d")
    yarin_str = yarin.strftime("%Y-%m-%d")
    ozel_str = ozel.strftime("%Y-%m-%d")
    
    print(Fore.CYAN + "\n📆 Tarih Seçin:")
    print(f"  1. Bugün - {bugun_str}")
    print(f"  2. Yarın - {yarin_str}")
    print(f"  3. Bir Sonraki Gün - {ozel_str}")
    
    while True:
        tarih_secim = input(Fore.CYAN + "Seçiminiz (1/2/3): ")
        if tarih_secim == "1":
            secilen_tarih = bugun_str
            break
        elif tarih_secim == "2":
            secilen_tarih = yarin_str
            break
        elif tarih_secim == "3":
            secilen_tarih = ozel_str
            break
        else:
            print(Fore.RED + "⚠️ Geçersiz seçim, lütfen 1, 2 veya 3 girin.")
    
    print(Fore.CYAN + "\n🏛️ Lütfen bir kat seçin:")
    print("  1. 💎 Zemin Kat")
    print("  2. 🌜 1. Kat")
    print("  3. 💩 Bodrum Kat")
    
    kat_secim = input(Fore.CYAN + "Seçiminiz (1/2/3): ").strip()
    kat_kodu = None
    kat_adi = ""
    
    if kat_secim == "1":
        kat_kodu = "82"
        kat_adi = "Zemin Kat"
    elif kat_secim == "2":
        kat_kodu = "80"
        kat_adi = "1. Kat"
    elif kat_secim == "3":
        kat_kodu = "81"
        kat_adi = "Bodrum Kat"
    else:
        print(Fore.RED + "⚠️ Geçersiz kat seçimi.")
        return
    
    print(Fore.CYAN + f"\n⏰ {kat_adi} için uygun seans saatleri:")
    seanslar = [("1", "Sabah (08:30 - 13:50)"), ("2", "Öğle (14:00 - 19:50)")]
    if kat_kodu != "80":
        seanslar.append(("3", "Akşam (20:00 - 23:50)"))
    
    for kod, saat in seanslar:
        print(f"  {kod}. 🕒 {saat}")
    
    seans_secim = input(Fore.CYAN + "Seçiminiz (1/2/3): ").strip()
    seans_kodu = None
    seans_dict = dict(seanslar)
    if seans_secim in seans_dict:
        seans_kodu = seans_secim
    else:
        print(Fore.RED + "⚠️ Geçersiz seans seçimi.")
        return
    
    print(Fore.GREEN + f"📌 Seçilen Kat: {kat_adi}, Seans: {seans_dict[seans_secim]}")
    
    empty_seats = check_empty_seats(session, headers, reservation_page_url, getir_token, secilen_tarih, kat_kodu, seans_kodu)
    
    if empty_seats:
        print(Fore.GREEN + f"\n{len(empty_seats)} adet boş koltuk bulundu:")
        for i, koltuk in enumerate(empty_seats, 1):
            print(f"{i}. Koltuk No: {koltuk}")
        try:
            secim = int(input(Fore.CYAN + "\n➡️ Rezervasyon yapılacak koltuğun numarasını girin: "))
            if 1 <= secim <= len(empty_seats):
                secilen_koltuk = empty_seats[secim - 1]
            else:
                print(Fore.RED + "⚠️ Geçersiz seçim, işlem iptal edildi.")
                return
        except ValueError:
            print(Fore.RED + "⚠️ Geçersiz giriş, işlem iptal edildi.")
            return
    else:
        print(Fore.YELLOW + "\nHiç boş koltuk yok, otomatik moda geçiliyor...")
        empty_seats = wait_for_empty_seat(session, headers, reservation_page_url, getir_token, secilen_tarih, kat_kodu, seans_kodu)
        secilen_koltuk = choose_random_seat(empty_seats)
        print(Fore.GREEN + f"Rastgele seçilen koltuk: {secilen_koltuk}")
    
    user.update({
        "kat": kat_kodu,
        "seans": seans_kodu,
        "masa": secilen_koltuk,
        "tarih": secilen_tarih
    })
    make_reservation(session, headers, yap_token, user, reservation_page_url)

if __name__ == "__main__":
    main_menu()