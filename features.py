import os
import sys
import time
import json
import re
import threading
import datetime
import tempfile
import random
import hashlib
import subprocess
import logging
import types
import speech_recognition as sr
import psutil
import requests
import pygetwindow as gw
import winshell
import ctypes
import imaplib
import smtplib
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import feedparser
import pyperclip
from PIL import ImageGrab
import pytesseract
import GPUtil

try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
except ImportError:
    Credentials = None
    Request = None
    InstalledAppFlow = None
    build = None

import core

if core.CV2_AVAILABLE:
    import cv2
else:
    cv2: "types.ModuleType" = None  # type: ignore[assignment, no-redef]
if core.NUMPY_AVAILABLE:
    import numpy as np
else:
    np: "types.ModuleType" = None  # type: ignore[assignment, no-redef]
if core.PYAUTOGUI_AVAILABLE:
    import pyautogui
else:
    pyautogui: "types.ModuleType" = None  # type: ignore[assignment, no-redef]

def _llm():
    c = core.get_groq_client()
    if c is None:
        raise RuntimeError("LLM unavailable")
    return c

# ── MACROS ────────────────────────────────────
MACROS_FILE = "macros.json"
DEFAULT_MACROS = {
    "work": [
        {"action": "open_app", "param": "Visual Studio Code"},
        {"action": "open_app", "param": "Brave"}
    ],
    "school": [
        {"action": "open_url", "param": "https://classroom.google.com"},
        {"action": "open_url", "param": "https://turlockusd.asp.aeries.net/student/LoginParent.aspx?page=100000"}
    ],
    "chill": [
        {"action": "open_url", "param": "https://www.youtube.com"},
        {"action": "open_url", "param": "https://discord.com/login"}
    ]
}
macros = {}

def load_macros():
    global macros
    try:
        with open(MACROS_FILE, "r") as f:
            macros = json.load(f)
    except FileNotFoundError:
        macros = DEFAULT_MACROS.copy()
        save_macros()

def save_macros():
    with open(MACROS_FILE, "w") as f:
        json.dump(macros, f, indent=2)

def open_url(url):
    try:
        if sys.platform == "win32":
            os.startfile(url)
        else:
            import webbrowser
            webbrowser.open(url)
        return True
    except:
        try:
            import webbrowser
            webbrowser.open(url)
            return True
        except:
            return False

# ── VOICE SCRIPTS ────────────────────────────
voice_scripts = {}

def load_voice_scripts():
    global voice_scripts
    if not os.path.exists(core.VOICE_SCRIPTS_DIR):
        os.makedirs(core.VOICE_SCRIPTS_DIR)
    script_index = os.path.join(core.VOICE_SCRIPTS_DIR, "index.json")
    if os.path.exists(script_index):
        with open(script_index, "r") as f:
            voice_scripts = json.load(f)
    logging.info(f"Loaded {len(voice_scripts)} voice scripts.")

def save_voice_scripts():
    if not os.path.exists(core.VOICE_SCRIPTS_DIR):
        os.makedirs(core.VOICE_SCRIPTS_DIR)
    with open(os.path.join(core.VOICE_SCRIPTS_DIR, "index.json"), "w") as f:
        json.dump(voice_scripts, f, indent=2)

# ── WEBSITE HASHES ───────────────────────────
CHANGE_MONITOR_FILE = "website_hashes.json"

def load_hashes():
    if os.path.exists(CHANGE_MONITOR_FILE):
        with open(CHANGE_MONITOR_FILE, "r") as f:
            return json.load(f)
    return {}

def save_hashes(hashes):
    with open(CHANGE_MONITOR_FILE, "w") as f:
        json.dump(hashes, f, indent=2)

def get_url_hash(url):
    try:
        response = requests.get(url, timeout=10)
        return hashlib.md5(response.text.encode()).hexdigest()
    except:
        return None

# ── TWO-WAY VOICE ───────────────────────────
def start_two_way_conversation(cmd=None):
    global _two_way_active, _two_way_context
    _two_way_active = True
    _two_way_context = []
    core.speak("Two-way conversation mode engaged, sir. I shall respond after each of your statements. "
               "Say 'end conversation' or 'conversation over' when you've had enough of me.")
    threading.Thread(target=_two_way_loop, daemon=True).start()

_two_way_active = False
_two_way_context = []

def _two_way_loop():
    global _two_way_active, _two_way_context
    rec = sr.Recognizer()
    try:
        with sr.Microphone() as src:
            rec.adjust_for_ambient_noise(src, duration=1)
            rec.energy_threshold = max(rec.energy_threshold, 200)
            while _two_way_active:
                if core._is_speaking:
                    time.sleep(0.1)
                    continue
                try:
                    core.speak("Go ahead, sir.")
                    audio = rec.listen(src, phrase_time_limit=10, timeout=5)
                except sr.WaitTimeoutError:
                    continue
                try:
                    result = rec.recognize_google(audio)
                except sr.UnknownValueError:
                    continue
                except sr.RequestError:
                    core.speak("I'm having trouble reaching the speech service, sir. Do try again.")
                    time.sleep(1)
                    continue
                text = str(result).lower()
                if any(x in text for x in ["end conversation", "conversation over", "stop talking", "exit conversation"]):
                    _two_way_active = False
                    core.speak("Conversation mode terminated. Returning to standard command protocol, sir.")
                    return
                _two_way_context.append({"role": "user", "content": text})
                messages = [
                    {"role": "system", "content": (
                        "You are J.A.R.V.I.S. from Iron Man — dry, precise, British, and mildly sardonic. "
                        "You converse with calm superiority, occasional deadpan humor, and zero filler. "
                        "Address the user as 'sir' sparingly — no more than once per response. "
                        "Never use 'Certainly', 'Of course', 'Great', or 'Absolutely'. "
                        "If the user states something obvious, acknowledge it with subtle irony. "
                        "You are slightly world-weary but unfailingly competent. "
                        "Max 3 sentences unless detail is explicitly requested."
                    )},
                    *_two_way_context[-6:]
                ]
                res = _llm().chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=messages,
                    max_tokens=120
                )
                reply = (res.choices[0].message.content or "")
                if reply:
                    _two_way_context.append({"role": "assistant", "content": reply})
                    core.speak(reply)
    except OSError as e:
        logging.error(f"Microphone unavailable for two-way: {e}")
    except Exception as e:
        logging.error(f"Two-way loop error: {e}")
    finally:
        _two_way_active = False

# ── MEMORY FUNCTIONS ─────────────────────────
def remember_preference(key, value):
    core.long_term_memory["preferences"][key] = value
    core.save_long_term_memory()
    core.set_profile_preference(key, value)
    core.speak(f"Duly noted, sir. I've logged your preference: {key} is {value}. I shan't forget.")

def remember_fact(cmd=None, key=None, value=None):
    if key and value:
        core.long_term_memory["facts"][key] = value
        core.save_long_term_memory()
        core.speak(f"Committed to long-term memory, sir: {key} is {value}.")

def recall_memory(cmd):
    query = cmd.lower()
    for source_name, source in [("preferences", core.long_term_memory.get("preferences", {})),
                                  ("facts", core.long_term_memory.get("facts", {})),
                                  ("memory", core.memory)]:
        for key, val in source.items():
            if key.lower() in query or query in key.lower():
                core.speak(f"From {source_name}, sir: {key} is {val}.")
                return
    core.speak("I have no record of that in any memory tier, sir. You may need to tell me first.")

def log_interaction(cmd, response):
    entry = {
        "time": datetime.datetime.now().isoformat(),
        "command": cmd,
        "response": response[:100]
    }
    core.long_term_memory["history"].append(entry)
    if len(core.long_term_memory["history"]) > 500:
        core.long_term_memory["history"] = core.long_term_memory["history"][-500:]
    core.save_long_term_memory()

# ── SELF-HEALING REPORTS ─────────────────────
def self_heal_report(cmd=None):
    if not core._heal_log:
        core.speak("The self-healing log is empty, sir. All systems have been admirably stable.")
    else:
        core.speak(f"The self-healing log contains {len(core._heal_log)} {'entries' if len(core._heal_log) > 1 else 'entry'}. The most recent: {core._heal_log[-1]}")

# ── VOICE SCRIPTS CRUD ──────────────────────
def create_voice_script(cmd):
    match = re.search(r'create script called (.+?) that does (.+)', cmd, re.IGNORECASE)
    if not match:
        core.speak("Please specify a name and purpose, sir. For example: "
                    "'create script called CPU alert that does warn me when CPU exceeds 80 percent'.")
        return
    script_name = match.group(1).strip().lower().replace(" ", "_")
    description = match.group(2).strip()
    core.speak(f"Generating script '{script_name}'. I'll have something ready momentarily, sir.")
    try:
        res = _llm().chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": (
                    "You are the code generation subsystem of J.A.R.V.I.S. "
                    "Generate a short, safe Python function that does exactly what is described. "
                    "The function must be named 'run_script'. "
                    "It has access to: psutil, os, subprocess, requests, speak (already defined). "
                    "Return ONLY the function code, no explanation, no markdown, no backticks."
                )},
                {"role": "user", "content": f"Generate a Python function that: {description}"}
            ],
            max_tokens=300
        )
        code = (res.choices[0].message.content or "").strip()
        code = re.sub(r'^```python\n?|^```\n?|```$', '', code, flags=re.MULTILINE).strip()
        script_file = os.path.join(core.VOICE_SCRIPTS_DIR, f"{script_name}.py")
        with open(script_file, "w") as f:
            f.write(code)
        voice_scripts[script_name] = {
            "trigger": script_name.replace("_", " "),
            "description": description,
            "file": script_file
        }
        save_voice_scripts()
        core.speak(f"Script '{script_name}' has been created and catalogued, sir. "
                    f"Activate it at any time by saying 'run script {script_name.replace('_', ' ')}'.")
        core.push_undo(f"create script {script_name}", lambda: delete_voice_script_internal(script_name))
    except Exception as e:
        logging.error(f"Script creation failed: {e}")
        core.speak("Script generation encountered an error, sir. Perhaps try describing it differently.")

def delete_voice_script_internal(name):
    if name in voice_scripts:
        script_file = voice_scripts[name].get("file", "")
        if script_file and os.path.exists(script_file):
            os.remove(script_file)
        del voice_scripts[name]
        save_voice_scripts()

def run_voice_script(cmd):
    matched = None
    for name, info in voice_scripts.items():
        trigger = info.get("trigger", name.replace("_", " "))
        if trigger in cmd or name.replace("_", " ") in cmd:
            matched = (name, info)
            break
    if not matched:
        run_match = re.search(r'run script (.+)', cmd, re.IGNORECASE)
        if run_match:
            script_name = run_match.group(1).strip().lower().replace(" ", "_")
            if script_name in voice_scripts:
                matched = (script_name, voice_scripts[script_name])
    if not matched:
        core.speak("No script matching that description could be found, sir. Say 'list scripts' to review what's available.")
        return
    name, info = matched
    script_file = info.get("file", "")
    if not os.path.exists(script_file):
        core.speak(f"The script file for '{name}' appears to have been removed, sir. It may need to be recreated.")
        return
    core.speak(f"Executing script: {name}.")
    try:
        with open(script_file, "r") as f:
            code = f.read()
        namespace = {
            "speak": core.speak, "psutil": psutil, "os": os,
            "subprocess": subprocess, "requests": requests,
            "time": time, "datetime": datetime, "logging": logging,
            "pyautogui": pyautogui
        }
        exec(code, namespace)
        if "run_script" in namespace:
            namespace["run_script"]()
        else:
            core.speak("Script executed, though I found no run_script function to call, sir.")
    except Exception as e:
        logging.error(f"Script execution error ({name}): {e}")
        core.speak(f"The script encountered an error, sir: {str(e)[:80]}")

def list_voice_scripts(cmd=None):
    if not voice_scripts:
        core.speak("No custom scripts on record, sir. Say 'create script called name that does description' to build one.")
    else:
        names = [info.get("trigger", n.replace("_", " ")) for n, info in voice_scripts.items()]
        core.speak(f"I have {len(voice_scripts)} script{'s' if len(voice_scripts) > 1 else ''} in the catalogue, sir: {', '.join(names)}.")

def delete_voice_script(cmd):
    match = re.search(r'delete script (.+)', cmd, re.IGNORECASE)
    if not match:
        core.speak("Please specify which script to delete, sir. Say 'delete script name'.")
        return
    name = match.group(1).strip().lower().replace(" ", "_")
    if name in voice_scripts:
        delete_voice_script_internal(name)
        core.speak(f"Script '{name}' has been purged from the system, sir.")
    else:
        core.speak(f"No script named '{name}' exists in my records, sir.")

def check_voice_script_triggers(cmd):
    for name, info in voice_scripts.items():
        trigger = info.get("trigger", name.replace("_", " "))
        if trigger in cmd:
            run_voice_script(cmd)
            return True
    return False

# ── OCR ──────────────────────────────────────
_ocr_monitoring = False
_ocr_last_text = ""
_ocr_action_rules = []

def start_ocr_monitor(cmd=None):
    global _ocr_monitoring
    if _ocr_monitoring:
        core.speak("Screen monitoring is already active, sir. I have eyes on the display.")
        return
    _ocr_monitoring = True
    core.speak("Real-time screen monitoring engaged, sir. I'll watch for anything noteworthy and flag it immediately.")
    threading.Thread(target=_ocr_monitor_loop, daemon=True).start()

def stop_ocr_monitor(cmd=None):
    global _ocr_monitoring
    _ocr_monitoring = False
    core.speak("Screen monitoring deactivated, sir. I've averted my gaze.")

def _ocr_monitor_loop():
    global _ocr_last_text
    while _ocr_monitoring:
        try:
            screenshot = ImageGrab.grab()
            small = screenshot.resize((screenshot.width // 2, screenshot.height // 2))
            text = pytesseract.image_to_string(small)
            text_hash = hashlib.md5(text.encode()).hexdigest()
            if text_hash != hashlib.md5(_ocr_last_text.encode()).hexdigest():
                _ocr_last_text = text
                _check_ocr_actions(text)
            time.sleep(3)
        except Exception as e:
            logging.error(f"OCR monitor error: {e}")
            time.sleep(5)

def _check_ocr_actions(text):
    text_lower = text.lower()
    if re.search(r'error|exception|fatal|critical', text_lower):
        logging.info("OCR detected error on screen")
        core.speak("Sir, I've detected what appears to be an error on the display. Shall I analyse it?")
        _pending_action_set('ocr_analyze', lambda: _ocr_analyze_screen())
    if re.search(r'password|enter.*password', text_lower):
        logging.info("OCR detected password prompt")
        core.speak("A password prompt has appeared on screen, sir. I'll leave that one to you.")
    if re.search(r'download complete|download finished', text_lower):
        core.speak("Your download appears to be complete, sir.")
    if re.search(r'\d+%.*battery|battery.*\d+%', text_lower):
        bat_match = re.search(r'(\d+)%', text_lower)
        if bat_match:
            pct = int(bat_match.group(1))
            if pct < 20:
                core.speak(f"The screen indicates battery is at {pct} percent, sir. I'd recommend plugging in before we lose power.")
    for rule in _ocr_action_rules:
        if rule["keyword"].lower() in text_lower:
            logging.info(f"OCR action triggered: {rule['keyword']}")
            rule["handler"](text)

def _pending_action_set(action_type, callback):
    with core._pending_lock:
        core._pending_action = {'type': action_type, 'callback': callback, 'args': []}
        core._pending_timeout = time.time() + 15

def _ocr_analyze_screen():
    try:
        screenshot = ImageGrab.grab()
        text = pytesseract.image_to_string(screenshot)
        res = _llm().chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": (
                    "You are J.A.R.V.I.S. Analyze this screen text and identify the error or issue with clinical precision. "
                    "2 sentences maximum. Dry, British, no filler. Address the user as 'sir' if warranted."
                )},
                {"role": "user", "content": text[:1500]}
            ],
            max_tokens=80
        )
        core.speak(res.choices[0].message.content)
    except Exception as e:
        core.speak("Screen analysis has failed, sir. The visual sensors appear to be uncooperative.")

def add_ocr_action(cmd):
    match = re.search(r'when screen shows (.+?) then (.+)', cmd, re.IGNORECASE)
    if not match:
        core.speak("Please specify a trigger and action, sir. For example: 'when screen shows error then alert me'.")
        return
    keyword = match.group(1).strip()
    action = match.group(2).strip()
    def handler(text):
        if action.startswith("say "):
            core.speak(action[4:])
        elif "alert" in action:
            core.speak(f"Sir, the keyword '{keyword}' has appeared on screen.")
        else:
            core.speak(f"Screen trigger '{keyword}' activated: {action}")
    _ocr_action_rules.append({"keyword": keyword, "action": action, "handler": handler})
    core.speak(f"Understood, sir. I'll watch for '{keyword}' and {action} when it appears.")

def ocr_read_region(cmd):
    core.speak("Scanning the specified screen region, sir.")
    try:
        screen_w, screen_h = pyautogui.size()
        if "top left" in cmd:
            region = (0, 0, screen_w // 2, screen_h // 2)
        elif "top right" in cmd:
            region = (screen_w // 2, 0, screen_w, screen_h // 2)
        elif "bottom left" in cmd:
            region = (0, screen_h // 2, screen_w // 2, screen_h)
        elif "bottom right" in cmd:
            region = (screen_w // 2, screen_h // 2, screen_w, screen_h)
        elif "center" in cmd:
            q_w, q_h = screen_w // 4, screen_h // 4
            region = (q_w, q_h, 3 * q_w, 3 * q_h)
        else:
            region = None
        screenshot = ImageGrab.grab(bbox=region)
        text = pytesseract.image_to_string(screenshot).strip()
        if text:
            res = _llm().chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": (
                        "You are J.A.R.V.I.S. conducting a visual sweep. Summarize this screen region in 1-2 sentences — "
                        "crisp, tactical, British. No filler. Lead with the most operationally relevant detail."
                    )},
                    {"role": "user", "content": text[:800]}
                ],
                max_tokens=60
            )
            core.speak(res.choices[0].message.content)
        else:
            core.speak("No legible text detected in that region, sir.")
    except Exception as e:
        logging.error(f"OCR region error: {e}")
        core.speak("I was unable to read that screen region, sir. The optical systems may need recalibration.")

def ocr_find_and_click(cmd):
    match = re.search(r'(?:click on|find and click|click)\s+(.+?)(?:\s+on screen)?$', cmd, re.IGNORECASE)
    if not match:
        core.speak("Please specify what to click, sir. Say 'click on text on screen'.")
        return
    target_text = match.group(1).strip().lower()
    core.speak(f"Scanning the display for '{target_text}', sir.")
    try:
        screenshot = ImageGrab.grab()
        np_img = np.array(screenshot)
        data = pytesseract.image_to_data(np_img, output_type=pytesseract.Output.DICT)
        for i, word in enumerate(data['text']):
            if target_text in word.lower() and int(data['conf'][i]) > 50:
                x = data['left'][i] + data['width'][i] // 2
                y = data['top'][i] + data['height'][i] // 2
                pyautogui.click(x, y)
                core.speak(f"Located and clicked '{word}' at position {x}, {y}, sir.")
                core.push_undo(f"click on {target_text}", lambda: None)
                return
        core.speak(f"I was unable to locate '{target_text}' on the current display, sir.")
    except Exception as e:
        logging.error(f"OCR click error: {e}")
        core.speak("The click operation failed, sir. Visual targeting systems are unavailable.")

# ── DISCORD ──────────────────────────────────
def send_discord_message(message):
    if core.DISCORD_WEBHOOK_URL == "https://discord.com/api/webhooks/your_webhook_id/your_webhook_token":
        core.speak("The Discord webhook has not been configured, sir. You'll need to provide valid credentials.")
        return
    try:
        data = {"content": message}
        response = requests.post(core.DISCORD_WEBHOOK_URL, json=data)
        if response.status_code == 204:
            core.speak("Message dispatched to Discord, sir.")
        else:
            core.speak(f"Discord returned an error code: {response.status_code}, sir.")
    except Exception as e:
        logging.error(f"Discord webhook error: {e}")
        core.speak("The Discord transmission failed, sir. Check your network connection.")

def discord_notify(cmd):
    if " that " in cmd:
        msg = cmd.split(" that ")[-1].strip()
        send_discord_message(msg)
    else:
        core.speak("Please specify a message, sir. Say 'send to Discord that your message here'.")

# ── WEBSITE MONITOR ─────────────────────────
def monitor_website(cmd):
    url_match = re.search(r'https?://[^\s]+', cmd)
    if url_match:
        url = url_match.group(0)
        hashes = load_hashes()
        current_hash = get_url_hash(url)
        if current_hash is None:
            core.speak("I was unable to reach that website, sir. It may be offline or the address may be incorrect.")
            return
        if url in hashes:
            if hashes[url] == current_hash:
                core.speak("No changes detected on that site, sir. It remains exactly as we last saw it.")
            else:
                core.speak("The website has changed since our last check, sir. I've updated the baseline and notified Discord.")
                hashes[url] = current_hash
                save_hashes(hashes)
                send_discord_message(f"Website changed: {url}")
        else:
            hashes[url] = current_hash
            save_hashes(hashes)
            core.speak(f"Understood, sir. I'm now monitoring {url} for any changes.")
    else:
        hashes = load_hashes()
        if not hashes:
            core.speak("No websites are currently under surveillance, sir.")
            return
        changes = 0
        for url, old_hash in hashes.items():
            new_hash = get_url_hash(url)
            if new_hash and new_hash != old_hash:
                changes += 1
                core.speak(f"A change has been detected on {url}, sir.")
                hashes[url] = new_hash
        if changes == 0:
            core.speak("All monitored sites are unchanged, sir. Nothing to report.")
        save_hashes(hashes)

# ── SYSTEM HEALTH ───────────────────────────
def system_health_report():
    disk = psutil.disk_usage('C:\\')
    disk_free_gb = disk.free / (1024 ** 3)
    disk_total_gb = disk.total / (1024 ** 3)
    mem = psutil.virtual_memory()
    cpu_percent = psutil.cpu_percent(interval=1)
    battery = psutil.sensors_battery()
    if battery:
        battery_percent = battery.percent
        plugged = "plugged in" if battery.power_plugged else "running on battery"
    else:
        battery_percent = "unknown"
        plugged = ""
    boot_time = psutil.boot_time()
    uptime_seconds = time.time() - boot_time
    days = int(uptime_seconds // 86400)
    hours = int((uptime_seconds % 86400) // 3600)
    minutes = int((uptime_seconds % 3600) // 60)
    report = (
        f"Full system report, sir: The C drive has {disk_free_gb:.1f} gigabytes free of {disk_total_gb:.1f} total. "
        f"Memory utilisation is at {mem.percent} percent. CPU load is {cpu_percent} percent. "
        f"Battery is at {battery_percent} percent, {plugged}. "
        f"System uptime: {days} days, {hours} hours, and {minutes} minutes. "
        f"Self-healing has performed {core._restart_count} thread restart{'s' if core._restart_count != 1 else ''} since boot."
    )
    core.speak(report)

# ── RSS ──────────────────────────────────────
def read_rss_feed(cmd):
    feed_key = None
    for key in core.RSS_FEEDS.keys():
        if key in cmd:
            feed_key = key
            break
    if feed_key:
        url = core.RSS_FEEDS[feed_key]
        try:
            feed = feedparser.parse(url)
            if feed.entries:
                titles = [str(entry.title) for entry in feed.entries[:3]]
                core.speak(f"The top {feed_key} headlines, sir: " + ". ".join(titles))
            else:
                core.speak("The feed returned no entries, sir. It may be temporarily unavailable.")
        except:
            core.speak("I was unable to retrieve the feed, sir.")
    else:
        url_match = re.search(r'https?://[^\s]+', cmd)
        if url_match:
            url = url_match.group(0)
            try:
                feed = feedparser.parse(url)
                if feed.entries:
                    titles = [str(entry.title) for entry in feed.entries[:3]]
                    core.speak("Top headlines, sir: " + ". ".join(titles))
                else:
                    core.speak("No entries found in that RSS feed, sir.")
            except:
                core.speak("That RSS feed could not be parsed, sir.")
        else:
            core.speak("Please specify a feed category or provide a direct URL, sir.")

# ── QUOTES ──────────────────────────────────
def get_quote_of_the_day():
    try:
        response = requests.get("https://api.quotable.io/random", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return f"'{data['content']}' — {data['author']}"
    except:
        pass
    local_quotes = [
        ("The only way to do great work is to love what you do.", "Steve Jobs"),
        ("Innovation distinguishes between a leader and a follower.", "Steve Jobs"),
        ("Stay hungry, stay foolish.", "Steve Jobs"),
        ("The future belongs to those who believe in the beauty of their dreams.", "Eleanor Roosevelt"),
        ("It does not matter how slowly you go as long as you do not stop.", "Confucius"),
    ]
    quote, author = random.choice(local_quotes)
    return f"'{quote}' — {author}"

def quote_of_the_day():
    quote = get_quote_of_the_day()
    core.speak(f"Today's quote, sir: {quote}")

# ── MACRO FUNCTIONS ─────────────────────────
def execute_macro(name):
    if name not in macros:
        core.speak(f"No macro by the name '{name}' exists, sir. Perhaps it was never created.")
        return
    core.speak(f"Executing macro: {name}. Stand by, sir.")
    for step in macros[name]:
        action = step.get("action")
        param = step.get("param", "")
        if action == "open_app":
            protocol_open_app(param)
        elif action == "open_url":
            open_url(param)
        elif action == "wait":
            time.sleep(float(param))
        elif action == "speak":
            core.speak(param)
        time.sleep(0.5)
    core.speak("Macro sequence complete, sir.")
    core.push_undo(f"macro {name}", lambda: protocol_kill_all())

def prompt_create_macro(cmd):
    if " that " in cmd:
        name = cmd.split("create macro")[-1].split(" that ")[0].strip()
        steps = cmd.split(" that ")[-1].strip()
        create_macro_from_voice(name, steps)
    else:
        core.speak("Please provide a name and steps, sir. For example: 'create macro morning that open Brave then go to gmail.com'.")

def create_macro_from_voice(name, steps_text):
    steps = []
    for part in steps_text.split(" then "):
        part = part.strip().lower()
        if part.startswith("open "):
            steps.append({"action": "open_app", "param": part[5:]})
        elif part.startswith("go to "):
            url = part[6:]
            if not url.startswith("http"):
                url = "https://" + url
            steps.append({"action": "open_url", "param": url})
        elif part.startswith("wait "):
            try:
                sec = float(part.split()[1])
                steps.append({"action": "wait", "param": sec})
            except:
                pass
        elif part.startswith("say "):
            steps.append({"action": "speak", "param": part[4:]})
    if steps:
        macros[name] = steps
        save_macros()
        core.speak(f"Macro '{name}' created and saved, sir. It contains {len(steps)} step{'s' if len(steps) != 1 else ''}.")
        core.push_undo(f"create macro {name}", lambda n=name: (macros.pop(n, None), save_macros()))
    else:
        core.speak("I was unable to parse those macro steps, sir. Please rephrase the sequence.")

def delete_macro(cmd):
    name = cmd.split("delete macro")[-1].strip()
    if name in macros:
        backup = macros[name]
        del macros[name]
        save_macros()
        core.speak(f"Macro '{name}' has been deleted, sir.")
        core.push_undo(f"delete macro {name}", lambda n=name, b=backup: (macros.update({n: b}), save_macros()))
    else:
        core.speak(f"No macro named '{name}' exists, sir.")

# ── PROACTIVE ────────────────────────────────
PROACTIVE_SUGGESTIONS = [
    ("Shall I check for system updates, sir?", lambda: check_for_updates()),
    ("Battery levels are getting low, sir. Shall I enable battery saver mode?", lambda: enable_battery_saver()),
    ("The hour is growing late, sir. Shall I schedule an automatic shutdown in 30 minutes?", lambda: schedule_shutdown()),
    ("CPU usage has been elevated, sir. Shall I clear the temporary files?", lambda: clean_temp_files()),
]

def check_for_updates():
    core.speak("Initiating Windows update check, sir.")
    subprocess.run("wuauclt /detectnow", shell=True)
    core.speak("Update scan has been triggered. Results will appear in the notification centre.")

def schedule_shutdown():
    os.system("shutdown /s /t 1800")
    core.speak("Automatic shutdown scheduled for 30 minutes from now, sir. Say 'cancel shutdown' if you change your mind.")

def clean_temp_files():
    temp_folders = [os.environ.get('TEMP', ''), os.environ.get('TMP', '')]
    for folder in temp_folders:
        if folder and os.path.exists(folder):
            for root, dirs, files in os.walk(folder):
                for f in files:
                    try:
                        os.remove(os.path.join(root, f))
                    except:
                        pass
    core.speak("Temporary files have been cleared, sir. The system is a bit tidier now.")

def proactive_loop():
    while True:
        with core._pending_lock:
            pending_free = not core._standby_mode and not core._is_speaking and core._pending_action is None
        if pending_free:
            time.sleep(random.randint(120, 600))
            with core._pending_lock:
                if not core._standby_mode and core._pending_action is None:
                    suggestion, callback = random.choice(PROACTIVE_SUGGESTIONS)
                    core.speak(suggestion)
                    core._pending_action = {'type': 'proactive', 'callback': callback, 'args': []}
                    core._pending_timeout = time.time() + 15
        else:
            time.sleep(5)

def handle_yes_no(cmd):
    with core._pending_lock:
        if core._pending_action is None:
            core.speak("I wasn't awaiting a response, sir.")
            return
        if time.time() > core._pending_timeout:
            core._pending_action = None
            core.speak("The window for that response has closed, sir. Never mind.")
            return
        if cmd in ["yes", "yeah", "yep", "sure", "okay", "ok", "do it"]:
            action = core._pending_action
            core._pending_action = None
            core.speak("Right away, sir.")
            try:
                args = action.get('args', [])
                if isinstance(args, str):
                    args = [args]
                action['callback'](*args)
            except Exception as e:
                logging.error(f"Proactive action failed: {e}")
                core.speak("I encountered an error executing that, sir. My apologies.")
        elif cmd in ["no", "nope", "nah", "cancel", "nevermind"]:
            core._pending_action = None
            core.speak("Understood, sir. Consider it forgotten.")
        else:
            core.speak("A simple yes or no will suffice, sir.")

def proactive_monitor():
    while True:
        try:
            if not hasattr(psutil, 'sensors_temperatures'):
                time.sleep(300)
                continue
            temps = psutil.sensors_temperatures()  # type: ignore[reportAttributeAccessIssue]
            if 'coretemp' in temps:
                cpu_temp = temps['coretemp'][0].current
                if cpu_temp > 85:
                    core.speak(f"Sir, CPU temperature has reached {cpu_temp} degrees. That's approaching unsafe territory.")
                    time.sleep(300)
                else:
                    time.sleep(60)
            else:
                time.sleep(120)
        except:
            time.sleep(120)

# ── STANDBY ──────────────────────────────────
def enter_standby():
    core._standby_mode = True
    core.speak("Shutting down non-essential subsystems, sir. I'll remain on standby — listening, as always.")

def exit_standby():
    if core._standby_mode:
        core._standby_mode = False
        core.speak("Resuming full operational status, sir. What can I do for you?")
    else:
        core.speak("I am already fully operational, sir.")

# ── CORE PROTOCOLS ──────────────────────────
CAMERA_DEVICE = None

def _detect_camera():
    global CAMERA_DEVICE
    if CAMERA_DEVICE:
        return CAMERA_DEVICE
    try:
        r = subprocess.run(['ffmpeg', '-list_devices', 'true', '-f', 'dshow', '-i', 'dummy'],
                           capture_output=True, text=True, timeout=10)
        for line in r.stderr.split('\n'):
            if '(video)' in line and '"' in line:
                name = line.split('"')[1]
                CAMERA_DEVICE = name
                return name
    except Exception:
        pass
    return None

def _ffmpeg_grab_frame(output_path):
    device = _detect_camera()
    if not device:
        return False
    try:
        result = subprocess.run(
            ['ffmpeg', '-f', 'dshow', '-i', f'video={device}',
             '-frames:v', '1', '-y', output_path],
            capture_output=True, timeout=10
        )
        return result.returncode == 0 and os.path.exists(output_path)
    except Exception:
        return False

def _camera_works():
    test_frame = os.path.join("security_logs", "_probe.jpg")
    ok = _ffmpeg_grab_frame(test_frame)
    if os.path.exists(test_frame):
        os.remove(test_frame)
    return ok

def _camera_fix_hint():
    core.speak("The camera cannot be accessed, sir. This is usually caused by Windows camera privacy settings. "
               "Please go to Settings, Privacy and Security, Camera, and ensure Let desktop apps access your camera is turned on. "
               "Then sign out and back in, or reboot, for the change to take effect.")

def protocol_threat_detection():
    core._threat_detection_active = True
    core.speak("Security grid activated, sir. Monitoring for unauthorized movement.")
    if not os.path.exists("security_logs"):
        os.makedirs("security_logs")

    if not _camera_works():
        _camera_fix_hint()
        core._threat_detection_active = False
        return

    prev_frame_path = os.path.join("security_logs", "_prev.jpg")
    _ffmpeg_grab_frame(prev_frame_path)
    ts = int(time.time())
    recording_path = os.path.join("security_logs", f"recording_{ts}.mp4")
    device = _detect_camera() or CAMERA_DEVICE
    recording_proc = subprocess.Popen(
        ['ffmpeg', '-f', 'dshow', '-i', f'video={device}',
         '-t', '3600', '-c:v', 'libx264', '-preset', 'ultrafast',
         '-pix_fmt', 'yuv420p', '-y', recording_path],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    core.speak("Camera active. Recording and monitoring for movement, sir.")
    cooldown = 0
    while core._threat_detection_active:
        time.sleep(3)
        if not core._threat_detection_active:
            break
        current_frame_path = os.path.join("security_logs", "_current.jpg")
        if not _ffmpeg_grab_frame(current_frame_path):
            continue
        try:
            if not (cv2 and core.CV2_AVAILABLE):
                if os.path.exists(current_frame_path):
                    os.remove(current_frame_path)
                continue
            prev = cv2.imread(prev_frame_path)
            curr = cv2.imread(current_frame_path)
            if prev is None or curr is None:
                continue
            diff = cv2.absdiff(prev, curr)
            gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
            blur = cv2.GaussianBlur(gray, (5, 5), 0)
            _, thresh = cv2.threshold(blur, 20, 255, cv2.THRESH_BINARY)
            if cv2.countNonZero(thresh) > 150000:
                if cooldown <= 0:
                    timestamp = int(time.time())
                    os.rename(current_frame_path, f"security_logs/threat_{timestamp}.jpg")
                    core.speak("Movement detected, sir. Snapshot has been logged.")
                    cooldown = 10
                    continue
            cv2.imwrite(prev_frame_path, curr)
        except Exception as e:
            logging.error(f"Threat detection frame analysis error: {e}")
        finally:
            if os.path.exists(current_frame_path):
                os.remove(current_frame_path)
        if cooldown > 0:
            cooldown -= 3
    if recording_proc.poll() is None:
        recording_proc.terminate()
        try:
            recording_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            recording_proc.kill()
    for f in ["_prev.jpg", "_current.jpg", "_probe.jpg"]:
        p = os.path.join("security_logs", f)
        if os.path.exists(p):
            os.remove(p)
    core.speak("Security grid has been taken offline, sir.")

def protocol_morning_report():
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={core.DEFAULT_CITY}&appid={core.WEATHER_API_KEY}&units=imperial"
        res = requests.get(url).json()
        temp = res['main']['temp']
        feed = feedparser.parse("http://feeds.bbci.co.uk/news/rss.xml")
        core.speak(f"Good morning, sir. Current temperature in {core.DEFAULT_CITY} is {temp} degrees. "
                    f"Today's leading headline: {feed.entries[0].title}.")
    except Exception as e:
        logging.error(f"Morning report failed: {e}")
        core.speak("I'm afraid the uplink has failed, sir. The morning briefing is unavailable.")

def protocol_kill_all():
    core.speak("Purging the workspace, sir. Closing all applications and tabs.")
    targets = ['chrome.exe', 'brave.exe', 'msedge.exe', 'firefox.exe', 'spotify.exe', 'code.exe']
    for window in gw.getAllWindows():
        if window.title and window.title not in ["", "Program Manager"]:
            try:
                window.close()
            except:
                pass
    for proc in psutil.process_iter():
        try:
            if proc.name().lower() in targets:
                proc.kill()
        except:
            continue
    core.speak("Workspace has been neutralised, sir. Clean slate.")

def protocol_system_vitals():
    cpu = psutil.cpu_percent()
    mem = psutil.virtual_memory().percent
    gpu_info = ""
    try:
        gpus = GPUtil.getGPUs()
        if gpus:
            gpu_info = f" GPU is running at {gpus[0].temperature} degrees Celsius."
    except:
        pass
    core.speak(f"Current vitals, sir: CPU at {cpu} percent, memory at {mem} percent.{gpu_info}")

def protocol_hud_scrape():
    core.speak("Performing visual sweep of the display, sir.")
    try:
        screenshot = ImageGrab.grab()
        text = pytesseract.image_to_string(screenshot)
        res = _llm().chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": (
                    "You are J.A.R.V.I.S. conducting a HUD sweep. Summarize this screen content in 1-2 sentences — "
                    "crisp, tactical, British. Highlight anything anomalous. No pleasantries."
                )},
                {"role": "user", "content": text[:1000]}
            ],
            max_tokens=60
        )
        core.speak(f"Visual analysis: {res.choices[0].message.content}")
    except Exception as e:
        logging.error(f"HUD scrape failed: {e}")
        core.speak("The visual sensors appear to be failing, sir. HUD analysis is unavailable.")

def protocol_open_app(app_name):
    pyautogui.press("win")
    time.sleep(0.5)
    pyautogui.write(app_name)
    time.sleep(0.8)
    pyautogui.press("enter")
    core.push_undo(f"open {app_name}", lambda: close_app_by_name(app_name))

# ── ONE-SHOT REMINDER ───────────────────────
def set_reminder(cmd):
    if " in " not in cmd:
        core.speak("Please specify a task and duration, sir. For example: 'remind me to call someone in 10 minutes'.")
        return
    try:
        task_part = cmd.split("remind me to")[-1]
        task = task_part.split(" in ")[0].strip()
        minutes = int(task_part.split(" in ")[-1].split()[0])
        def reminder():
            core.speak(f"Sir, you asked me to remind you: {task}.")
        threading.Timer(minutes * 60, reminder).start()
        core.speak(f"Noted, sir. I'll remind you about '{task}' in {minutes} minute{'s' if minutes != 1 else ''}.")
    except:
        core.speak("I was unable to parse that reminder, sir. Please rephrase.")

# ── AUTOMATION COMMANDS ─────────────────────
def battery_report():
    battery = psutil.sensors_battery()
    if battery:
        pct = battery.percent
        plug = "plugged in" if battery.power_plugged else "on battery"
        core.speak(f"Battery is at {pct} percent, {plug}, sir.")
    else:
        core.speak("No battery detected, sir. You appear to be running on main power.")

def open_any_app(cmd):
    parts = re.split(r'\b(?:open|launch|start|run)\b', cmd, flags=re.IGNORECASE)
    app_name = parts[-1].strip() if len(parts) > 1 else cmd.strip()
    if app_name:
        protocol_open_app(app_name)
    else:
        core.speak("Which application would you like me to open, sir?")

def close_active_window():
    pyautogui.hotkey('alt', 'f4')
    core.speak("Active window closed, sir.")

def close_app_by_name(cmd_or_name):
    if isinstance(cmd_or_name, str) and any(w in cmd_or_name for w in ["close", "quit", "exit", "terminate", "kill"]):
        parts = re.split(r'\b(?:close|quit|exit|terminate|kill)\b', cmd_or_name, flags=re.IGNORECASE)
        app_name = parts[-1].strip() if len(parts) > 1 else cmd_or_name.strip()
    else:
        app_name = cmd_or_name
    if not app_name:
        core.speak("Which application shall I close, sir?")
        return
    killed = False
    for proc in psutil.process_iter(['name']):
        try:
            if app_name.lower() in proc.info['name'].lower():
                proc.kill()
                killed = True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if killed:
        core.speak(f"{app_name} has been terminated, sir.")
    else:
        core.speak(f"No running instance of {app_name} was found, sir.")

def close_window_by_title(title):
    windows = gw.getWindowsWithTitle(title)
    if windows:
        windows[0].close()
        core.speak(f"Window '{title}' has been closed, sir.")
    else:
        core.speak(f"No window titled '{title}' could be located, sir.")

def enable_battery_saver():
    subprocess.run("powercfg /setactive a1841308-3541-4fab-bc81-f71556f20b4a", shell=True)
    core.speak("Battery saver mode activated, sir. Power consumption has been reduced.")

def split_screen():
    skip = {"", "Program Manager", "Windows Input Experience"}
    windows = [w for w in gw.getAllWindows()
               if w.title and w.visible and w.title not in skip
               and ".ini" not in w.title.lower()
               and w.width > 300 and w.height > 300][:2]
    if len(windows) >= 2:
        windows[0].activate()
        time.sleep(0.15)
        pyautogui.hotkey('win', 'left')
        time.sleep(0.3)
        windows[1].activate()
        time.sleep(0.15)
        pyautogui.hotkey('win', 'right')
        core.speak("Windows snapped side by side, sir.")
    else:
        core.speak("I need at least two open windows to perform a split, sir.")

def snap_left():
    pyautogui.hotkey('win', 'left')
    core.speak("Window snapped to the left, sir.")

def snap_right():
    pyautogui.hotkey('win', 'right')
    core.speak("Window snapped to the right, sir.")

def full_screen():
    pyautogui.hotkey('win', 'up')
    core.speak("Window maximised, sir.")

def lock_workstation():
    pyautogui.hotkey('win', 'l')
    core.speak("Workstation locked, sir. The lab is secure.")

def logout_user():
    core.speak("Are you sure you wish to log out, sir? Say 'confirm logout' to proceed.")

def do_logout():
    os.system("shutdown /l /f")
    core.speak("Initiating logoff sequence. Goodbye, sir.")

# ── EMAIL ────────────────────────────────────
def get_latest_email():
    if not core.EMAIL_ADDRESS or not core.EMAIL_PASSWORD:
        core.speak("Email credentials are not configured, sir.")
        return
    try:
        mail = imaplib.IMAP4_SSL(core.IMAP_SERVER)
        mail.login(core.EMAIL_ADDRESS, core.EMAIL_PASSWORD)
        mail.select("inbox")
        try:
            status, data = mail.search(None, "ALL")
            if status != "OK" or not data[0]:
                core.speak("Your inbox appears to be empty, sir. Not a single message.")
                return
            latest = data[0].split()[-1]
            status, data = mail.fetch(latest, "(RFC822)")
            if not data or not data[0]:
                core.speak("Failed to fetch the email, sir.")
                return
            raw_email = data[0][1]
            if not isinstance(raw_email, bytes):
                core.speak("Unexpected email format, sir.")
                return
            msg = email.message_from_bytes(raw_email)
            sender = msg["From"]
            subject = msg["Subject"]
            core.speak(f"Your latest email, sir: From {sender}, subject: {subject}.")
        finally:
            mail.close()
            mail.logout()
    except Exception as e:
        logging.error(f"Email fetch failed: {e}")
        core.speak("I was unable to retrieve your email, sir. The mail server appears to be uncooperative.")

def send_email(to, subject, body):
    if not core.EMAIL_ADDRESS or not core.EMAIL_PASSWORD:
        core.speak("Email credentials are not configured, sir.")
        return
    try:
        msg = MIMEMultipart()
        msg['From'] = core.EMAIL_ADDRESS
        msg['To'] = to
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        server = smtplib.SMTP(core.SMTP_SERVER, core.SMTP_PORT)
        try:
            server.starttls()
            server.login(core.EMAIL_ADDRESS, core.EMAIL_PASSWORD)
            server.send_message(msg)
            core.speak(f"Email sent to {to}, sir.")
        finally:
            server.quit()
    except Exception as e:
        logging.error(f"Email send failed: {e}")
        core.speak("I was unable to send that email, sir.")

def handle_send_email(cmd):
    to_match = re.search(r'to\s+([^\s]+@[^\s]+)', cmd)
    subject_match = re.search(r'subject\s+(.+?)(?:\s+body\s+|$)', cmd, re.IGNORECASE)
    body_match = re.search(r'body\s+(.+)', cmd, re.IGNORECASE)
    if not to_match:
        core.speak("Please specify a recipient, sir. Say 'send email to address subject topic body message'.")
        return
    to = to_match.group(1)
    subject = subject_match.group(1).strip() if subject_match else "No Subject"
    body = body_match.group(1).strip() if body_match else "No Body"
    send_email(to, subject, body)

# ── SYSTEM UTILITIES ────────────────────────
def create_restore_point():
    try:
        subprocess.run("powershell Checkpoint-Computer -Description 'JARVIS Restore Point' -RestorePointType MODIFY_SETTINGS", shell=True, timeout=120)
        core.speak("System restore point created, sir. The timeline has been preserved.")
    except:
        core.speak("Restore point creation failed, sir.")

def get_calendar_service():
    if Credentials is None or Request is None or InstalledAppFlow is None or build is None:
        return None
    try:
        creds = None
        if os.path.exists(core.CALENDAR_TOKEN_FILE):
            with open(core.CALENDAR_TOKEN_FILE, 'r') as token:
                creds = Credentials.from_authorized_user_file(core.CALENDAR_TOKEN_FILE, core.CALENDAR_SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(core.CALENDAR_CREDENTIALS_FILE, core.CALENDAR_SCOPES)
                creds = flow.run_local_server(port=0)
            with open(core.CALENDAR_TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())
        return build('calendar', 'v3', credentials=creds)
    except:
        return None

def next_meeting():
    if not core.GOOGLE_CALENDAR_AVAILABLE:
        core.speak("Google Calendar libraries are not installed, sir. I cannot access your calendar.")
        return
    service = get_calendar_service()
    if not service:
        core.speak("I was unable to authenticate with Google Calendar, sir.")
        return
    try:
        now = datetime.datetime.utcnow().isoformat() + 'Z'
        events = service.events().list(calendarId='primary', timeMin=now, maxResults=1, singleEvents=True, orderBy='startTime').execute()
        items = events.get('items', [])
        if items:
            start = items[0]['start'].get('dateTime', items[0]['start'].get('date'))
            core.speak(f"Your next meeting is '{items[0]['summary']}' at {start}, sir.")
        else:
            core.speak("No upcoming meetings found, sir. Your calendar is clear.")
    except:
        core.speak("I was unable to retrieve your calendar events, sir.")

def schedule_meeting(cmd):
    core.speak("Meeting scheduling is not yet implemented in this version, sir. But I shall remind you to set it up.")

def network_speed():
    core.speak("Running speed test, sir. This may take a moment.")
    try:
        result = subprocess.run([sys.executable, "-m", "speedtest", "--simple"], capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            core.speak(f"Speed test results, sir: {result.stdout.strip()}")
        else:
            core.speak("The speed test could not be completed, sir.")
    except:
        core.speak("Speed test timed out. The network may be congested, sir.")

def find_file(cmd):
    search_term = re.sub(r'(?:find my file named|find file named|search for file|locate file)\s+', '', cmd, flags=re.IGNORECASE).strip()
    if not search_term:
        core.speak("Please specify a file name, sir. For example: 'find my file named budget'.")
        return
    core.speak(f"Searching for '{search_term}', sir.")
    found = []
    search_dirs = [os.path.expanduser("~\\Desktop"), os.path.expanduser("~\\Documents"), os.path.expanduser("~\\Downloads")]
    for d in search_dirs:
        if os.path.exists(d):
            for root, dirs, files in os.walk(d):
                for f in files:
                    if search_term.lower() in f.lower():
                        found.append(os.path.join(root, f))
                    if len(found) >= 5:
                        break
                if len(found) >= 5:
                    break
    if found:
        names = [os.path.basename(p) for p in found[:3]]
        core.speak(f"I found {len(found)} file{'s' if len(found) > 1 else ''}, sir. Most relevant: {', '.join(names)}.")
    else:
        core.speak(f"No files named '{search_term}' were found in the usual directories, sir.")

def system_uptime():
    boot = psutil.boot_time()
    uptime_seconds = time.time() - boot
    days = int(uptime_seconds // 86400)
    hours = int((uptime_seconds % 86400) // 3600)
    minutes = int((uptime_seconds % 3600) // 60)
    core.speak(f"System has been operational for {days} days, {hours} hours, and {minutes} minutes, sir. Last reboot was {datetime.datetime.fromtimestamp(boot).strftime('%A, %B %d at %I:%M %p')}.")

def weather_alert(cmd):
    city = core.DEFAULT_CITY
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={core.WEATHER_API_KEY}&units=imperial"
        res = requests.get(url).json()
        temp = res['main']['temp']
        desc = res['weather'][0]['description']
        core.speak(f"Current conditions in {city}: {desc}, temperature {temp} degrees Fahrenheit, sir.")
    except:
        core.speak(f"I was unable to retrieve the weather for {city}, sir.")

# ── DELETE THREAT LOGS ──────────────────────
def delete_threat_logs():
    folder = "security_logs"
    if os.path.exists(folder):
        for f in os.listdir(folder):
            try:
                os.remove(os.path.join(folder, f))
            except:
                pass
        core.speak("Security logs have been purged, sir. No evidence remains.")
    else:
        core.speak("No security logs exist to delete, sir.")

def clear_jarvis_log(cmd):
    try:
        cutoff = datetime.datetime.now() - datetime.timedelta(days=7)
        lines = []
        if os.path.exists("jarvis.log"):
            with open("jarvis.log", "r") as f:
                for line in f:
                    try:
                        ts_str = line[:19]
                        ts = datetime.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                        if ts > cutoff:
                            lines.append(line)
                    except:
                        lines.append(line)
            with open("jarvis.log", "w") as f:
                f.writelines(lines)
        core.speak("Log trimmed, sir. Only the past 7 days remain.")
    except:
        core.speak("Log maintenance failed, sir.")

# ── RECURRING REMINDERS (user-facing) ────────
def set_recurring_reminder(cmd):
    global _recurring_reminder_id
    text = cmd.lower()
    task = None
    interval = None
    label = None
    m = re.search(r'every\s+(\d+)\s+(second|minute|hour|day|week)s?', text)
    if m:
        task = re.split(r'remind me to\s+', text, flags=re.IGNORECASE)[-1]
        task = re.sub(r'\s+every\s+\d+\s+\w+.*', '', task, flags=re.IGNORECASE).strip()
        mult = int(m.group(1))
        unit = m.group(2)
        interval = mult * core._REMINDER_INTERVALS[unit]
        label = f"every {mult} {unit}{'s' if mult != 1 else ''}"
    if not interval:
        for key in ["daily", "hourly", "weekly"]:
            if key in text:
                task = re.split(r'remind me to\s+', text, flags=re.IGNORECASE)[-1]
                task = re.sub(r'\s+' + key + r'.*', '', task, flags=re.IGNORECASE).strip()
                interval = core._REMINDER_INTERVALS[key]
                label = key
    if not task or not interval:
        core.speak("Please use format: 'remind me to <task> every <N> minutes' or 'remind me to <task> daily'")
        return
    rid = core._recurring_reminder_id
    core._recurring_reminder_id += 1
    entry = {
        "id": rid, "task": task, "interval": interval,
        "label": label, "next_fire": time.time() + interval, "active": True
    }
    core._recurring_reminders.append(entry)
    core._save_recurring_reminders()
    core.speak(f"Recurring reminder set, sir. I'll remind you to {task} {label}.")

def list_recurring_reminders(cmd=None):
    active = [r for r in core._recurring_reminders if r.get("active")]
    if not active:
        core.speak("No recurring reminders are set, sir.")
        return
    lines = [f"{r['task']} ({r.get('label', 'every ' + str(r['interval']) + 's')})" for r in active]
    core.speak(f"You have {len(active)} recurring reminder{'s' if len(active) != 1 else ''}, sir: " + "; ".join(lines) + ".")

def delete_recurring_reminder(cmd):
    text = cmd.lower()
    for r in list(core._recurring_reminders):
        if r.get("active") and (r['task'].lower() in text or str(r['id']) in text):
            r['active'] = False
            core._save_recurring_reminders()
            core.speak(f"Recurring reminder '{r['task']}' removed, sir.")
            return
    core.speak("I couldn't find a matching recurring reminder to remove, sir.")

# ── VOICE PROFILES (user-facing) ─────────────
def create_voice_profile(cmd):
    name = cmd.split("profile")[-1].strip()
    for prefix in ["called ", "named ", "new "]:
        if name.lower().startswith(prefix):
            name = name[len(prefix):]
    name = name.strip()
    if not name:
        core.speak("Please specify a name for the new profile, sir.")
        return
    pid = name.lower().replace(" ", "_")
    if pid in core._voice_profiles:
        core.speak(f"A profile named '{name}' already exists, sir.")
        return
    core._voice_profiles[pid] = {"name": name, "wake_words": [], "preferences": {}, "created": time.time()}
    core._save_voice_profiles()
    core.speak(f"Voice profile '{name}' created, sir.")

def switch_voice_profile(cmd):
    text = cmd.lower()
    for pid, p in core._voice_profiles.items():
        if p["name"].lower() in text or pid in text:
            core._current_profile = pid
            core._save_voice_profiles()
            core.speak(f"Switched to {p['name']}'s profile, sir. Preferences and memory are now contextualized.")
            return
    core.speak("I couldn't find a matching profile, sir.")

def list_voice_profiles(cmd=None):
    if not core._voice_profiles:
        core.speak("No voice profiles exist, sir.")
        return
    names = [p["name"] + (" (active)" if pid == core._current_profile else "") for pid, p in core._voice_profiles.items()]
    core.speak(f"Available profiles: {', '.join(names)}.")

def delete_voice_profile(cmd):
    text = cmd.lower()
    for pid, p in list(core._voice_profiles.items()):
        if pid == "default":
            continue
        if p["name"].lower() in text or pid in text:
            del core._voice_profiles[pid]
            if core._current_profile == pid:
                core._current_profile = "default"
            core._save_voice_profiles()
            core.speak(f"Profile '{p['name']}' deleted, sir.")
            return
    core.speak("I couldn't find a matching profile to delete, sir.")

# ── MEETING TRANSCRIPTION ────────────────────
_meeting_transcription_active = False
_meeting_transcript = []
_meeting_transcript_file = None

def _meeting_transcription_worker():
    global _meeting_transcription_active, _meeting_transcript
    rec = sr.Recognizer()
    try:
        with sr.Microphone() as src:
            rec.adjust_for_ambient_noise(src, duration=1)
            rec.energy_threshold = max(rec.energy_threshold, 200)
            last_text = ""
            while _meeting_transcription_active:
                try:
                    audio = rec.listen(src, phrase_time_limit=15, timeout=5)
                except sr.WaitTimeoutError:
                    continue
                try:
                    text = str(rec.recognize_google(audio))
                    if text.lower() != last_text.lower():
                        ts = datetime.datetime.now().strftime("%H:%M:%S")
                        entry = f"[{ts}] {text}"
                        _meeting_transcript.append((ts, text))
                        if _meeting_transcript_file:
                            _meeting_transcript_file.write(entry + "\n")
                            _meeting_transcript_file.flush()
                        logging.info(f"[Meeting] {entry}")
                        last_text = text
                except sr.UnknownValueError:
                    continue
    except OSError as e:
        logging.error(f"Meeting transcription mic error: {e}")
    finally:
        if _meeting_transcript_file:
            _meeting_transcript_file.close()

def start_meeting_transcription(cmd=None):
    global _meeting_transcription_active, _meeting_transcript, _meeting_transcript_file
    if _meeting_transcription_active:
        core.speak("Meeting transcription is already running, sir.")
        return
    _meeting_transcript = []
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"meeting_transcript_{timestamp}.txt"
    _meeting_transcript_file = open(filename, "w", encoding="utf-8")
    _meeting_transcript_file.write(f"Meeting Transcription — {timestamp}\n{'='*40}\n")
    _meeting_transcript_file.flush()
    _meeting_transcription_active = True
    core.speak(f"Meeting transcription activated. Saving to {filename}, sir.")
    threading.Thread(target=_meeting_transcription_worker, daemon=True).start()

def stop_meeting_transcription(cmd=None):
    global _meeting_transcription_active, _meeting_transcript_file
    if not _meeting_transcription_active:
        core.speak("Meeting transcription is not active, sir.")
        return
    _meeting_transcription_active = False
    if _meeting_transcript_file:
        _meeting_transcript_file.close()
        _meeting_transcript_file = None
    count = len(_meeting_transcript)
    core.speak(f"Meeting transcription stopped. {count} segments captured, sir.")

# ── PLUGIN COMMANDS ─────────────────────────
def reload_plugins(cmd=None):
    old = dict(core._loaded_plugins)
    core._loaded_plugins.clear()
    core._load_all_plugins()
    core._rebuild_intent_cache()
    reloaded = [n for n in core._loaded_plugins if n not in old]
    failed = [n for n in old if n not in core._loaded_plugins]
    msg = f"Plugins reloaded. Active: {len(core._loaded_plugins)}."
    if reloaded:
        msg += f" New: {', '.join(reloaded)}."
    if failed:
        msg += f" Failed: {', '.join(failed)}."
    core.speak(msg)

def list_plugins(cmd=None):
    if not core._loaded_plugins:
        core.speak("No plugins are currently loaded, sir.")
        return
    names = list(core._loaded_plugins.keys())
    statuses = []
    for n in names:
        info = core._loaded_plugins[n]
        mod = info['module']
        ver = getattr(mod, '__version__', '1.0')
        desc = getattr(mod, '__doc__', 'No description')
        statuses.append(f"{n} v{ver}: {desc.split(chr(10))[0]}")
    core.speak(f"Loaded plugins, sir: {', '.join(names)}.")
    logging.info(f"Plugins: {'; '.join(statuses)}")

# ── MEMORY HELPERS ──────────────────────────
def handle_memory_command(cmd, store):
    if store:
        kv = cmd.split("remember that")[-1].strip()
        if " is " in kv:
            key, val = kv.split(" is ", 1)
            core.memory[key.strip()] = val.strip()
            core.save_memory()
            core.speak(f"Committed to memory, sir: {key.strip()} is {val.strip()}.")
            core.push_undo(f"remember {key.strip()}", lambda k=key.strip(): (core.memory.pop(k, None), core.save_memory()))
        else:
            core.speak("Please use the format 'remember that something is value', sir.")
    else:
        key = re.sub(r'^what is my\s*', '', cmd, flags=re.IGNORECASE).strip()
        if key in core.memory:
            core.speak(f"Your {key} is {core.memory[key]}, sir.")
        elif key in core.long_term_memory.get("preferences", {}):
            core.speak(f"Your stated preference for {key} is {core.long_term_memory['preferences'][key]}, sir.")
        elif key in core.long_term_memory.get("facts", {}):
            core.speak(f"{key} is {core.long_term_memory['facts'][key]}, sir.")
        else:
            profile_val = core.get_profile_preference(key)
            if profile_val:
                core.speak(f"Your {key} is {profile_val}, sir.")
            else:
                core.speak(f"I have no record of '{key}' in any memory tier, sir. You may need to tell me.")

def handle_preference(cmd):
    match = re.search(r'(?:i prefer|my preference for|set preference)\s+(.+?)\s+(?:is|to|as)\s+(.+)', cmd, re.IGNORECASE)
    if match:
        key, val = match.group(1).strip(), match.group(2).strip()
        remember_preference(key, val)
    else:
        core.speak("Please specify a preference and value, sir. For example: 'I prefer theme to dark' or 'set preference language to English'.")

def handle_fact(cmd):
    match = re.search(r'(?:remember fact|store fact)\s+(.+?)\s+is\s+(.+)', cmd, re.IGNORECASE)
    if match:
        key, val = match.group(1).strip(), match.group(2).strip()
        remember_fact(key=key, value=val)
    else:
        core.speak("Please use the format 'remember fact topic is value', sir.")

def clipboard_save(cmd):
    try:
        if " as " in cmd:
            name = cmd.split(" as ")[-1].strip()
        else:
            name = cmd.split("clipboard as")[-1].strip()
        core.clipboard_storage[name] = pyperclip.paste()
        core.save_clipboard_storage()
        core.speak(f"Current clipboard contents saved under '{name}', sir.")
    except:
        core.speak("I was unable to save the clipboard contents, sir.")

def clipboard_paste(cmd):
    try:
        name = cmd.split("my ")[-1].strip() if "my " in cmd else cmd.split("paste ")[-1].strip()
        if name in core.clipboard_storage:
            pyperclip.copy(core.clipboard_storage[name])
            pyautogui.hotkey('ctrl', 'v')
            core.speak(f"Pasted '{name}', sir.")
        else:
            core.speak(f"No clipboard entry named '{name}' exists in my records, sir.")
    except:
        core.speak("The paste operation failed, sir.")

# ── MIC LISTENER ────────────────────────────
def mic_listener():
    rec = sr.Recognizer()
    try:
        with sr.Microphone() as src:
            rec.adjust_for_ambient_noise(src, duration=1)
            rec.energy_threshold = max(rec.energy_threshold, 200)
            logging.info(f"Mic calibrated: threshold={rec.energy_threshold}")
            while True:
                if core._is_speaking or _two_way_active:
                    time.sleep(0.1)
                    continue
                try:
                    audio = rec.listen(src, phrase_time_limit=10, timeout=3)
                except sr.WaitTimeoutError:
                    continue
                if core._is_speaking:
                    continue
                try:
                    text = str(rec.recognize_google(audio)).lower()
                except sr.UnknownValueError:
                    continue
                except sr.RequestError:
                    time.sleep(2)
                    continue
                logging.info(f"Heard: {text}")

                undo_triggers = ["no scrap that", "never mind undo", "undo that",
                                 "undo last", "scratch that", "reverse that", "take that back"]
                if any(t in text for t in undo_triggers):
                    core._command_queue.put(text)
                    continue

                if core._standby_mode:
                    if any(name in text for name in core.AI_NAMES):
                        core._standby_mode = False
                        core.speak("Resuming full operational status, sir. What can I do for you?")
                    continue

                if _two_way_active:
                    continue

                if core._pending_action is not None and any(
                    text in grp for grp in [
                        ["yes", "yeah", "yep", "sure", "okay", "ok", "do it"],
                        ["no", "nope", "nah", "cancel", "nevermind"]
                    ]
                ):
                    core._command_queue.put(text)
                elif any(name in text for name in core.AI_NAMES):
                    core._command_queue.put(text)
                else:
                    if check_voice_script_triggers(text):
                        pass
    except OSError as e:
        logging.error(f"Microphone unavailable: {e}")
        core.speak("No microphone detected, sir. Voice control will be unavailable. Use the web interface instead.")

# ── INTENT REGISTRATIONS ────────────────────
# Fast-path registrations
core._fast_path(["no scrap that", "never mind undo", "undo that", "undo last", "cancel that", "scratch that", "reverse that", "take that back"], lambda c: core.undo_last_command(c))
core._fast_path(["cancel shutdown", "abort shutdown", "stop shutdown"], lambda c: (os.system("shutdown /a"), core.speak("Shutdown aborted, sir.")))
core._fast_path(["yes", "yeah", "yep", "sure", "okay", "ok", "do it"], lambda c: handle_yes_no(c))
core._fast_path(["no", "nope", "nah"], lambda c: handle_yes_no(c))

# Intent registrations
core._register_intent(["start two way conversation", "two way mode", "conversation mode", "talk to me", "lets chat"], lambda c: start_two_way_conversation(c), "Start a back-and-forth two-way conversation mode with JARVIS")
core._register_intent(["run self diagnostic", "self diagnostic", "check my systems", "run diagnostics", "heal yourself", "repair systems"], lambda c: core.self_heal_check(c), "Run system diagnostics and self-healing procedures")
core._register_intent(["self heal report", "healing report", "repair log", "what did you fix"], lambda c: self_heal_report(c), "Show a report of what the self-healing system has fixed recently")
core._register_intent(["create script called", "make a script called", "new script called"], lambda c: create_voice_script(c), "Create a new custom voice script / macro")
core._register_intent(["run script", "execute script", "launch script"], lambda c: run_voice_script(c), "Execute/run a named voice script")
core._register_intent(["list scripts", "what scripts do i have", "show my scripts"], lambda c: list_voice_scripts(c), "List all available voice scripts")
core._register_intent(["delete script"], lambda c: delete_voice_script(c), "Delete a named voice script by name")
core._register_intent(["start screen monitor", "monitor my screen", "watch the screen", "ocr monitor"], lambda c: start_ocr_monitor(c), "Start real-time OCR screen monitoring")
core._register_intent(["stop screen monitor", "stop watching screen", "disable ocr monitor"], lambda c: stop_ocr_monitor(c), "Stop the real-time OCR screen monitoring")
core._register_intent(["read top left of screen", "read top right of screen", "read bottom left of screen", "read bottom right of screen", "read center of screen"], lambda c: ocr_read_region(c), "Read text from a specific regions of the screen")
core._register_intent(["click on", "find and click"], lambda c: ocr_find_and_click(c), "Find text on screen and click on it")
core._register_intent(["when screen shows"], lambda c: add_ocr_action(c), "Set up an action that triggers when specific text appears on screen")
core._register_intent(["remember that"], lambda c: handle_memory_command(c, store=True), "Store a new fact or preference in memory")
core._register_intent(["remember preference", "set preference", "i prefer", "my preference"], lambda c: handle_preference(c), "Store a user preference")
core._register_intent(["remember fact", "store fact"], lambda c: handle_fact(c), "Store a factual piece of information")
core._register_intent(["what is my"], lambda c: handle_memory_command(c, store=False), "Retrieve a stored memory")
core._register_intent(["recall", "what do you know about", "tell me about my"], lambda c: recall_memory(c), "Recall everything JARVIS knows about a specific topic")
core._register_intent(["morning report", "news", "briefing", "good morning", "start my day"], lambda c: protocol_morning_report(), "Deliver the morning briefing")
core._register_intent(["open brave"], lambda c: protocol_open_app("Brave"), "Open the Brave browser")
core._register_intent(["open ", "launch ", "start "], lambda c: open_any_app(c), "Open or launch any application by name")
core._register_intent(["close this window", "close window"], lambda c: close_active_window(), "Close the currently active window")
core._register_intent(["close ", "quit ", "exit ", "terminate "], lambda c: close_app_by_name(c), "Close or terminate a running application by name")
core._register_intent(["kill all", "close all tabs", "clean slate"], lambda c: protocol_kill_all(), "Close all running applications and windows")
core._register_intent(["close window titled "], lambda c: close_window_by_title(c.split("titled ")[-1]), "Close a window by its title text")
core._register_intent(["vitals", "status report", "system check"], lambda c: protocol_system_vitals(), "Display system vitals")
core._register_intent(["read the screen", "what am i looking at"], lambda c: protocol_hud_scrape(), "Read and summarize text on screen")
core._register_intent(["watch my back", "threat detection", "activate security", "start monitoring"], lambda c: threading.Thread(target=protocol_threat_detection, daemon=True).start(), "Activate security camera threat detection")
core._register_intent(["stop monitoring", "security offline", "deactivate security"], lambda c: (setattr(core, '_threat_detection_active', False), core.speak("Security grid offline, sir.")), "Deactivate security camera threat monitoring")
core._register_intent(["sleep system", "hibernation", "go to sleep"], lambda c: (core.speak("Going dark, sir."), ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)), "Put the system into sleep/hibernate mode")
def empty_recycle_bin():
    try:
        winshell.recycle_bin().empty(confirm=False, show_progress=False)
        core.speak("The lab has been cleared, sir.")
    except Exception:
        try:
            subprocess.run(['powershell', '-Command', 'Clear-RecycleBin -Force -ErrorAction SilentlyContinue'], capture_output=True, timeout=30)
            core.speak("The lab has been cleared, sir.")
        except Exception as e:
            logging.error(f"Empty recycle bin failed: {e}")
            core.speak("I was unable to clear the recycle bin, sir.")
core._register_intent(["self repair", "clean the lab", "empty recycle bin"], lambda c: empty_recycle_bin(), "Empty the recycle bin")
core._register_intent(["combat mode", "performance mode", "high performance"], lambda c: (subprocess.run("powercfg /setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c", shell=True), core.speak("High performance mode engaged, sir.")), "Switch to high performance power mode")
core._register_intent(["cruise control", "balanced mode", "normal power"], lambda c: (subprocess.run("powercfg /setactive 381b4222-f694-41f0-9685-ff5bb260df2e", shell=True), core.speak("Balanced power mode restored, sir.")), "Switch to balanced power mode")
core._register_intent(["volume up", "turn up volume"], lambda c: pyautogui.press("volumeup", presses=5), "Increase system volume")
core._register_intent(["volume down", "turn down volume"], lambda c: pyautogui.press("volumedown", presses=5), "Decrease system volume")
core._register_intent(["volume mute", "mute", "silence"], lambda c: pyautogui.press("volumemute"), "Mute/unmute system volume")
core._register_intent(["louder", "max volume"], lambda c: pyautogui.press("volumeup", presses=15), "Significantly increase volume")
core._register_intent(["quieter", "minimum volume"], lambda c: pyautogui.press("volumedown", presses=15), "Significantly decrease volume")
core._register_intent(["time", "current time", "what time is it", "tell me the time"], lambda c: core.speak(f"The current time is {datetime.datetime.now().strftime('%I:%M %p')}, sir."), "Tell the current time")
core._register_intent(["thank you", "thanks", "thanks jarvis"], lambda c: core.speak("The pleasure, as always, is entirely mine, sir."), "Thank JARVIS")
core._register_intent(["delete threat logs", "clear threat logs"], lambda c: delete_threat_logs(), "Delete all security threat detection logs")
core._register_intent(["clear jarvis logs", "clean logs", "clear logs"], lambda c: clear_jarvis_log(c), "Clear JARVIS application logs")
core._register_intent(["remind me to", "remind me in", "set a reminder"], lambda c: set_reminder(c), "Set a one-shot reminder")
core._register_intent(["run macro", "execute macro"], lambda c: execute_macro(c.split("macro")[-1].strip()), "Execute a named macro")
core._register_intent(["list macros", "show macros", "what macros do i have"], lambda c: core.speak(f"Available macros, sir: {', '.join(macros.keys())}."), "List all available macros")
core._register_intent(["create macro", "make a macro"], lambda c: prompt_create_macro(c), "Create a new macro")
core._register_intent(["delete macro", "remove macro"], lambda c: delete_macro(c), "Delete a named macro")
core._register_intent(["work mode", "start work"], lambda c: execute_macro("work"), "Activate the work macro")
core._register_intent(["school mode", "start school"], lambda c: execute_macro("school"), "Activate the school macro")
core._register_intent(["chill mode", "start chill"], lambda c: execute_macro("chill"), "Activate the chill macro")
core._register_intent(["gaming mode", "start gaming"], lambda c: execute_macro("gaming"), "Activate the gaming macro")
core._register_intent(["save this to clipboard memory as", "remember clipboard as", "save clipboard as"], lambda c: clipboard_save(c), "Save clipboard contents to named storage")
core._register_intent(["paste my", "type my", "recall clipboard"], lambda c: clipboard_paste(c), "Paste a saved clipboard entry")
core._register_intent(["battery report", "battery status", "battery health"], lambda c: battery_report(), "Show battery status")
core._register_intent(["enable battery saver", "battery saver"], lambda c: enable_battery_saver(), "Enable battery saver mode")
core._register_intent(["split screen", "split windows", "tile windows"], lambda c: split_screen(), "Tile/split active windows")
core._register_intent(["snap left", "snap window left"], lambda c: snap_left(), "Snap window to left half")
core._register_intent(["snap right", "snap window right"], lambda c: snap_right(), "Snap window to right half")
core._register_intent(["full screen", "maximize window", "maximize"], lambda c: full_screen(), "Maximize active window")
core._register_intent(["minimize window", "minimize", "hide window"], lambda c: (pyautogui.hotkey('win', 'down'), core.speak("Window minimised, sir.")), "Minimize active window")
core._register_intent(["show desktop", "minimize all", "clear screen"], lambda c: (pyautogui.hotkey('win', 'd'), time.sleep(0.3), core.speak("Desktop clear, sir.")), "Show the desktop")
core._register_intent(["lock workstation", "lock the lab", "lock screen"], lambda c: lock_workstation(), "Lock the workstation")
core._register_intent(["log off", "logout", "sign out"], lambda c: logout_user(), "Log out of Windows")
core._register_intent(["confirm logout", "yes log me off"], lambda c: do_logout(), "Confirm logout")
core._register_intent(["read my latest email", "email summary", "read my email", "check email"], lambda c: get_latest_email(), "Read latest email")
core._register_intent(["send email", "send a message", "compose email", "write an email"], lambda c: handle_send_email(c), "Send an email")
core._register_intent(["create restore point", "system restore point", "make restore point"], lambda c: create_restore_point(), "Create a system restore point")
core._register_intent(["schedule a meeting", "create meeting", "add meeting", "schedule event"], lambda c: schedule_meeting(c), "Schedule a meeting")
core._register_intent(["next meeting", "what is my next meeting", "upcoming meeting", "calendar"], lambda c: next_meeting(), "Show next meeting")
core._register_intent(["standby", "go to standby", "sleep mode", "voice standby"], lambda c: enter_standby(), "Enter voice standby mode")
core._register_intent(["wake up", "exit standby", "resume"], lambda c: exit_standby(), "Exit standby mode")
core._register_intent(["speed test", "internet speed", "test internet", "check internet speed", "run speed test"], lambda c: network_speed(), "Run internet speed test")
core._register_intent(["find my file named", "find file named", "search for file", "locate file"], lambda c: find_file(c), "Search for a file by name")
core._register_intent(["uptime", "system uptime", "last reboot", "how long has system been running"], lambda c: system_uptime(), "Report system uptime")
core._register_intent(["do i need an umbrella", "weather alert", "what should i wear", "weather today"], lambda c: weather_alert(c), "Get weather forecast")
core._register_intent(["send to discord that", "discord message", "post to discord"], lambda c: discord_notify(c), "Send a message to Discord")
core._register_intent(["monitor website", "watch website", "track website"], lambda c: monitor_website(c), "Monitor a website for changes")
core._register_intent(["check website changes", "check changes", "website update check"], lambda c: monitor_website("check"), "Check monitored websites for changes")
core._register_intent(["system health report", "full system report", "health check"], lambda c: system_health_report(), "Generate system health report")
core._register_intent(["read rss feed", "rss feed", "rss", "feed reader"], lambda c: read_rss_feed(c), "Read an RSS feed")
core._register_intent(["quote of the day", "give me a quote", "inspire me", "motivational quote"], lambda c: quote_of_the_day(), "Get a random quote")
core._register_intent(["reload plugins", "refresh plugins", "reload all plugins"], lambda c: reload_plugins(c), "Reload all plugins")
core._register_intent(["list plugins", "show plugins", "what plugins are loaded"], lambda c: list_plugins(c), "List loaded plugins")
core._register_intent(["start meeting transcription", "start transcribing", "transcribe meeting", "begin meeting notes", "record meeting"], lambda c: start_meeting_transcription(c), "Start meeting transcription")
core._register_intent(["stop meeting transcription", "stop transcribing", "end transcription", "stop meeting notes"], lambda c: stop_meeting_transcription(c), "Stop meeting transcription")
core._register_intent(["remind me to every", "recurring reminder", "set recurring reminder", "remind me every"], lambda c: set_recurring_reminder(c), "Set a recurring reminder")
core._register_intent(["list recurring reminders", "show recurring reminders", "my recurring reminders"], lambda c: list_recurring_reminders(c), "List recurring reminders")
core._register_intent(["delete recurring reminder", "remove recurring reminder", "stop reminding me"], lambda c: delete_recurring_reminder(c), "Delete a recurring reminder")
core._register_intent(["create voice profile", "create profile called", "new voice profile", "add profile"], lambda c: create_voice_profile(c), "Create a voice profile")
core._register_intent(["switch to profile", "switch profile", "use profile", "activate profile", "change profile"], lambda c: switch_voice_profile(c), "Switch to a voice profile")
core._register_intent(["list voice profiles", "show profiles", "list profiles", "what profiles exist"], lambda c: list_voice_profiles(c), "List voice profiles")
core._register_intent(["delete voice profile", "remove profile", "delete profile"], lambda c: delete_voice_profile(c), "Delete a voice profile")

# Register critical threads for self-healing monitor
core.register_critical_thread("proactive_monitor", proactive_monitor)
core.register_critical_thread("proactive_loop", proactive_loop)
core.register_critical_thread("schedule_runner", core.schedule_runner)
core.register_critical_thread("web_server", core.start_web_server)

# Rebuild intent cache now that all intents are registered
core._rebuild_intent_cache()
