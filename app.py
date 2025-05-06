from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from colorama import init, Fore
import json
import os
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageEnhance, ImageOps
import pytesseract
from io import BytesIO
import re
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import threading
import time
from zoneinfo import ZoneInfo
import uuid

from son import (
    load_profiles, save_profiles, choose_profile, start_session, get_php_sessid,
    get_token, get_captcha_image, solve_captcha, login_user, get_reservation_tokens,
    check_empty_seats, make_reservation, create_subscription, edit_subscription,
    cancel_subscription, run_daily_reservations, KAT_KOLTUKLARI,
    wait_for_empty_seat, choose_random_seat
)

app = Flask(__name__)
app.secret_key = "super_secret_key"

# Tarama durumlarını saklamak için global sözlük
search_status = {}
# Aktif thread'leri saklamak için sözlük
search_threads = {}

# Otomatik rezervasyon için scheduler
scheduler = BackgroundScheduler(timezone=ZoneInfo("Europe/Istanbul"))
scheduler.add_job(run_daily_reservations, 'interval', days=1, start_date=datetime.now().replace(hour=9, minute=21, second=0))
scheduler.start()

# Ana sayfa (menü)
@app.route('/')
def index():
    return render_template('index.html')

# Giriş sayfası
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        name = request.form.get('name', username)
        save_profile = request.form.get('save_profile') == 'on'

        session, headers = start_session()
        PHPSESSID = get_php_sessid(session, headers)
        if not PHPSESSID:
            flash('PHPSESSID alınamadı!', 'error')
            return redirect(url_for('login'))

        token, giris_url = get_token(session, headers)
        success = login_user(session, headers, token, giris_url, username, password)
        if success:
            if save_profile:
                profiles = load_profiles()
                profiles.append({
                    'username': username,
                    'password': password,
                    'name': name,
                    'abonelik': []
                })
                save_profiles(profiles)
                flash(f'Profil kaydedildi: {name}', 'success')
            return redirect(url_for('reservation', username=username))
        else:
            flash('Giriş başarısız! Kullanıcı adı veya şifre hatalı.', 'error')
            return redirect(url_for('login'))
    return render_template('login.html')

# Kayıtlı profiller
@app.route('/profiles', methods=['GET', 'POST'])
def profiles():
    profiles = load_profiles()
    if request.method == 'POST':
        profile_index = int(request.form['profile']) - 1
        if 0 <= profile_index < len(profiles):
            username = profiles[profile_index]['username']
            action = request.args.get('action')
            if action == 'subscriptions':
                return redirect(url_for('subscriptions', username=username))
            return redirect(url_for('reservation', username=username))
        flash('Geçersiz profil seçimi!', 'error')
    return render_template('profiles.html', profiles=profiles)

def run_search_task(search_id, username, date, kat_kodu, seans_kodu, session, headers, getir_token, yap_token, reservation_page_url):
    """Arka planda tarama işlemini çalıştırır ve durumu günceller."""
    try:
        search_status[search_id] = {
            'status': 'running',
            'message': 'Boş koltuk kontrol ediliyor...',
            'empty_seats': [],
            'selected_seat': None,
            'reservation_result': None
        }

        # Onay metni imzalama (varsa)
        onay_token = get_reservation_tokens(session, headers)[2]
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
            if "teşekkürler" not in response_onay.text.lower():
                search_status[search_id] = {
                    'status': 'error',
                    'message': 'Onay metni imzalanamadı!',
                    'empty_seats': [],
                    'selected_seat': None,
                    'reservation_result': None
                }
                return

        # Otomatik koltuk arama
        max_attempts = 10000
        wait_time = 2
        for attempt in range(max_attempts):
            # İptal kontrolü
            if search_status[search_id].get('status') == 'cancelled':
                print(Fore.RED + f"⚠️ Tarama ({search_id}) iptal edildi, işlem durduruluyor.")
                return

            print(Fore.YELLOW + f"Boş koltuk kontrol ediliyor... (Deneme {attempt + 1}/{max_attempts})")
            empty_seats = check_empty_seats(session, headers, reservation_page_url, getir_token, date, kat_kodu, seans_kodu)
            
            # İptal kontrolü (tarama sonrası)
            if search_status[search_id].get('status') == 'cancelled':
                print(Fore.RED + f"⚠️ Tarama ({search_id}) iptal edildi, işlem durduruluyor.")
                return

            if empty_seats:
                print(Fore.GREEN + f"Boş Koltuklar: {', '.join(empty_seats)}")
                selected_seat = choose_random_seat(empty_seats)
                user = {
                    "username": username,
                    "password": load_profiles()[next(i for i, p in enumerate(load_profiles()) if p['username'] == username)]['password'],
                    "seans": seans_kodu,
                    "kat": kat_kodu,
                    "masa": selected_seat,
                    "tarih": date
                }
                response = make_reservation(session, headers, yap_token, user, reservation_page_url)
                if response and "rezervasyon işlemi başarılı." in response.text.lower():
                    search_status[search_id] = {
                        'status': 'success',
                        'message': f'Rezervasyon başarıyla yapıldı! Koltuk: {selected_seat}',
                        'empty_seats': empty_seats,
                        'selected_seat': selected_seat,
                        'reservation_result': 'success'
                    }
                else:
                    error_message = response.text if response else 'Sunucu yanıtı alınamadı.'
                    search_status[search_id] = {
                        'status': 'error',
                        'message': f'Rezervasyon başarısız oldu: {error_message}',
                        'empty_seats': empty_seats,
                        'selected_seat': selected_seat,
                        'reservation_result': 'failed'
                    }
                return
            else:
                print(Fore.RED + "Bu katta şu anda boş koltuk bulunmamaktadır. Tekrar deneniyor...")
                time.sleep(wait_time)
        
        # Maksimum deneme sayısına ulaşıldı
        search_status[search_id] = {
            'status': 'error',
            'message': 'Maksimum deneme sayısına ulaşıldı, boş koltuk bulunamadı.',
            'empty_seats': [],
            'selected_seat': None,
            'reservation_result': None
        }
    except Exception as e:
        search_status[search_id] = {
            'status': 'error',
            'message': f'Tarama sırasında hata oluştu: {str(e)}',
            'empty_seats': [],
            'selected_seat': None,
            'reservation_result': None
        }
    finally:
        # Thread'i temizle
        if search_id in search_threads:
            del search_threads[search_id]

@app.route('/reservation/<username>', methods=['GET', 'POST'])
def reservation(username):
    profiles = load_profiles()
    profile = next((p for p in profiles if p['username'] == username), None)
    if not profile:
        flash('Profil bulunamadı!', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        date = request.form.get('date')
        kat_kodu = request.form.get('kat')
        seans_kodu = request.form.get('seans')
        selected_seat = request.form.get('seat')

        session, headers = start_session()
        PHPSESSID = get_php_sessid(session, headers)
        if not PHPSESSID:
            flash('PHPSESSID alınamadı!', 'error')
            return redirect(url_for('reservation', username=username))

        token, giris_url = get_token(session, headers)
        success = login_user(session, headers, token, giris_url, profile['username'], profile['password'])
        if not success:
            flash('Giriş başarısız!', 'error')
            return redirect(url_for('reservation', username=username))

        getir_token, yap_token, onay_token, reservation_page_url = get_reservation_tokens(session, headers)
        if not getir_token or not yap_token:
            flash('Tokenler alınamadı!', 'error')
            return redirect(url_for('reservation', username=username))

        if selected_seat:
            user = {
                "username": profile['username'],
                "password": profile['password'],
                "seans": seans_kodu,
                "kat": kat_kodu,
                "masa": selected_seat,
                "tarih": date
            }
            try:
                response = make_reservation(session, headers, yap_token, user, reservation_page_url)
                if response is None:
                    flash('❌ Rezervasyon işlemi başarısız: Sunucu yanıtı alınamadı.', 'error')
                    return redirect(url_for('reservation', username=username))

                text = response.text.lower()
                if "rezervasyon işlemi başarılı." in text:
                    flash("🎉 Rezervasyon başarıyla yapıldı!", 'success')
                elif "zaten bir rezervasyonunuz bulunmaktadır." in text:
                    flash("⚠️ Bu seans için zaten bir rezervasyonunuz var.", 'warning')
                elif "rezervasyon için müsait değil." in text:
                    flash("⛔ Seçilen koltuk başkası tarafından alınmış.", 'error')
                elif "onay metni imzalanmamış." in text:
                    flash("✍ Onay metni imzalanmamış.", 'warning')
                else:
                    flash(f"❌ Rezervasyon başarısız oldu. Sunucu yanıtı: {text}", 'error')
            except Exception as e:
                flash(f"❌ Rezervasyon sırasında hata oluştu: {str(e)}", 'error')
            return redirect(url_for('reservation', username=username))

        empty_seats = check_empty_seats(session, headers, reservation_page_url, getir_token, date, kat_kodu, seans_kodu)
        if empty_seats:
            return render_template('reservation.html', username=username, empty_seats=empty_seats, date=date, kat=kat_kodu, seans=seans_kodu)
        else:
            search_id = str(uuid.uuid4())
            thread = threading.Thread(
                target=run_search_task,
                args=(search_id, profile['username'], date, kat_kodu, seans_kodu, session, headers, getir_token, yap_token, reservation_page_url)
            )
            thread.daemon = True
            search_threads[search_id] = thread
            thread.start()
            return render_template('reservation.html', username=username, empty_seats=[], date=date, kat=kat_kodu, seans=seans_kodu, search_id=search_id)

    return render_template('reservation.html', username=username)

@app.route('/check_status/<search_id>', methods=['GET'])
def check_status(search_id):
    status = search_status.get(search_id, {
        'status': 'error',
        'message': 'Tarama bulunamadı.',
        'empty_seats': [],
        'selected_seat': None,
        'reservation_result': None
    })
    return jsonify(status)

@app.route('/cancel_search/<search_id>', methods=['POST'])
def cancel_search(search_id):
    if search_id in search_status:
        search_status[search_id] = {
            'status': 'cancelled',
            'message': 'Tarama iptal edildi.',
            'empty_seats': [],
            'selected_seat': None,
            'reservation_result': None
        }
        if search_id in search_threads:
            del search_threads[search_id]
        return jsonify({'success': True, 'message': 'Tarama iptal edildi.'})
    return jsonify({'success': False, 'message': 'Tarama bulunamadı.'}), 404
    
# Abonelik yönetimi
@app.route('/subscriptions/<username>', methods=['GET', 'POST'])
def subscriptions(username):
    profiles = load_profiles()
    profile = next((p for p in profiles if p['username'] == username), None)
    if not profile:
        flash('Profil bulunamadı!', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        action = request.form.get('action')
        try:
            if action == 'create':
                result = create_subscription(username, profiles)
                if "error" in result:
                    flash(result["error"], 'error')
                else:
                    flash(result.get("success", "Abonelik oluşturuldu!"), 'success')
            elif action == 'edit':
                result = edit_subscription(username, profiles)
                if "error" in result:
                    flash(result["error"], 'error')
                else:
                    flash(result.get("success", "Abonelik düzenlendi!"), 'success')
            elif action == 'cancel':
                result = cancel_subscription(username, profiles)
                if "error" in result:
                    flash(result["error"], 'error')
                else:
                    flash(result.get("success", "Abonelik iptal edildi!"), 'success')
            else:
                flash('Geçersiz işlem!', 'error')
            save_profiles(profiles)
        except Exception as e:
            flash(f'Abonelik işlemi sırasında hata oluştu: {str(e)}', 'error')
        return redirect(url_for('subscriptions', username=username))

    # GET isteği için abonelik ve koltuk verilerini al
    subscription_data = cancel_subscription(username, profiles)
    koltuk_data = create_subscription(username, profiles)
    return render_template('subscriptions.html', profile=profile, subscription_data=subscription_data, koltuklar=koltuk_data.get('koltuklar', []))
    
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)