import speech_recognition as sr
import edge_tts
import asyncio
import pygame
import webbrowser
import pyautogui
import os
import sys
import time
import psutil
import threading
import queue
import datetime
import tempfile
import requests
import cv2
import pytesseract
import pygetwindow as gw
import ctypes
import GPUtil
import subprocess
import pythoncom
import feedparser
import winshell
import shutil
import glob
import numpy as np
import json
import logging
import schedule
import pyperclip
import random
import imaplib
import smtplib
import email
import re
import pickle
import hashlib
import inspect
import traceback
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from PIL import ImageGrab, Image
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from comtypes import CLSCTX_ALL
from ctypes import cast, POINTER, wintypes
from deepface import DeepFace
from groq import Groq
from flask import Flask, request, render_template_string
import socket
import scipy.fft
import scipy.signal
import os
from dotenv import load_dotenv

# Optional Google Calendar
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    GOOGLE_CALENDAR_AVAILABLE = True
except ImportError:
    GOOGLE_CALENDAR_AVAILABLE = False
    logging.warning("Google Calendar libraries not installed.")

# ──────────────────────────────────────────────
#  LOGGING
# ──────────────────────────────────────────────
logging.basicConfig(filename='jarvis.log', level=logging.INFO,
                    format='%(asctime)s %(levelname)s:%(message)s')

# ──────────────────────────────────────────────
#  CONFIGURATION
# ──────────────────────────────────────────────
AI_NAMES = ["jarvis", "buddy", "computer", "sir", "boss"]
load_dotenv()

GROQ_CLIENT = Groq(api_key=os.environ.get("GROQ_API_KEY"))
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")
DEFAULT_CITY = os.environ.get("DEFAULT_CITY", "London")  # fallback

EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

# Tesseract path – allow override, otherwise try common defaults
tesseract_path = os.environ.get("TESSERACT_PATH")
if tesseract_path:
    pytesseract.pytesseract.tesseract_cmd = tesseract_path
else:
    # Optionally warn but don't crash
    logging.warning("Tesseract not configured. OCR features will be unavailable.")
    
IMAP_SERVER = "imap.gmail.com"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/your_webhook_id/your_webhook_token"

CALENDAR_CREDENTIALS_FILE = "credentials.json"
CALENDAR_TOKEN_FILE = "token.json"
CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]

RSS_FEEDS = {
    "general": "http://feeds.bbci.co.uk/news/rss.xml",
    "tech": "http://feeds.bbci.co.uk/news/technology/rss.xml",
    "business": "http://feeds.bbci.co.uk/news/business/rss.xml",
    "sports": "http://feeds.bbci.co.uk/sport/rss.xml",
    "science": "http://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
    "hackernews": "https://hnrss.org/frontpage",
    "reddit": "https://www.reddit.com/r/all/.rss"
}

# Voice-activated scripts directory
VOICE_SCRIPTS_DIR = "voice_scripts"

# Self-healing config
SELF_HEAL_CHECK_INTERVAL = 300  # seconds
CRITICAL_MODULES = [
    "speech_recognition", "edge_tts", "pygame",
    "pyautogui", "psutil", "requests", "cv2",
    "pytesseract", "feedparser", "groq"
]

# ──────────────────────────────────────────────
#  GLOBALS
# ──────────────────────────────────────────────
chat_history = []
_threat_detection_active = False
_is_speaking = False
_command_queue = queue.Queue()
_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_loop)

pygame.mixer.init()

_standby_mode = False
_pending_action = None
_pending_timeout = 0

# ══════════════════════════════════════════════
#  ★ UNDO / "NO SCRAP THAT" SYSTEM
# ══════════════════════════════════════════════
_last_action_stack = []
_last_typed_text = ""
_last_opened_app = ""
_last_opened_url = ""

def push_undo(description, undo_fn):
    _last_action_stack.append((description, undo_fn))
    if len(_last_action_stack) > 10:
        _last_action_stack.pop(0)
    logging.info(f"Undo registered: {description}")

def undo_last_command(cmd=None):
    if not _last_action_stack:
        speak("The slate is already clean, sir. Nothing to reverse.")
        return
    description, undo_fn = _last_action_stack.pop()
    speak(f"Reversing the last action: {description}. Stand by.")
    try:
        undo_fn()
        speak("Done. The timeline has been corrected.")
    except Exception as e:
        logging.error(f"Undo failed: {e}")
        speak("I'm afraid that particular action is irreversible, sir. Some things cannot be undone.")

def undo_typed_text():
    global _last_typed_text
    if _last_typed_text:
        for _ in range(len(_last_typed_text)):
            pyautogui.hotkey('backspace')
        _last_typed_text = ""
    else:
        speak("There is no typed text on record to undo, sir.")

# ══════════════════════════════════════════════
#  ★ TWO-WAY VOICE
# ══════════════════════════════════════════════
_two_way_active = False
_two_way_context = []

def start_two_way_conversation(cmd=None):
    global _two_way_active, _two_way_context
    _two_way_active = True
    _two_way_context = []
    speak("Two-way conversation mode engaged, sir. I shall respond after each of your statements. "
          "Say 'end conversation' or 'conversation over' when you've had enough of me.")
    threading.Thread(target=_two_way_loop, daemon=True).start()

def _two_way_loop():
    global _two_way_active, _two_way_context
    rec = sr.Recognizer()
    while _two_way_active:
        if _is_speaking:
            time.sleep(0.1)
            continue
        try:
            with sr.Microphone() as src:
                rec.adjust_for_ambient_noise(src, duration=0.3)
                speak("Go ahead, sir.")
                audio = rec.listen(src, phrase_time_limit=8)
            text = rec.recognize_google(audio).lower()
            if any(x in text for x in ["end conversation", "conversation over", "stop talking", "exit conversation"]):
                _two_way_active = False
                speak("Conversation mode terminated. Returning to standard command protocol, sir.")
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
            res = GROQ_CLIENT.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                max_tokens=120
            )
            reply = res.choices[0].message.content
            _two_way_context.append({"role": "assistant", "content": reply})
            speak(reply)
        except sr.UnknownValueError:
            pass
        except Exception as e:
            logging.error(f"Two-way loop error: {e}")
            time.sleep(1)

# ══════════════════════════════════════════════
#  ★ PERSISTENT MEMORY (Enhanced)
# ══════════════════════════════════════════════
MEMORY_FILE = "jarvis_memory.json"
CLIPBOARD_FILE = "clipboard_storage.json"
LONG_TERM_MEMORY_FILE = "jarvis_longterm.json"
memory = {}
clipboard_storage = {}
long_term_memory = {}

def load_memory():
    global memory, long_term_memory
    try:
        with open(MEMORY_FILE, "r") as f:
            memory = json.load(f)
    except:
        memory = {}
    try:
        with open(LONG_TERM_MEMORY_FILE, "r") as f:
            long_term_memory = json.load(f)
    except:
        long_term_memory = {
            "preferences": {},
            "facts": {},
            "history": [],
            "reminders_completed": []
        }

def save_memory():
    try:
        with open(MEMORY_FILE, "w") as f:
            json.dump(memory, f, indent=2)
    except:
        pass

def save_long_term_memory():
    try:
        with open(LONG_TERM_MEMORY_FILE, "w") as f:
            json.dump(long_term_memory, f, indent=2)
    except:
        pass

def remember_preference(key, value):
    long_term_memory["preferences"][key] = value
    save_long_term_memory()
    speak(f"Duly noted, sir. I've logged your preference: {key} is {value}. I shan't forget.")

def remember_fact(cmd=None, key=None, value=None):
    if key and value:
        long_term_memory["facts"][key] = value
        save_long_term_memory()
        speak(f"Committed to long-term memory, sir: {key} is {value}.")

def recall_memory(cmd):
    query = cmd.lower()
    for source_name, source in [("preferences", long_term_memory.get("preferences", {})),
                                  ("facts", long_term_memory.get("facts", {})),
                                  ("memory", memory)]:
        for key, val in source.items():
            if key.lower() in query or query in key.lower():
                speak(f"From {source_name}, sir: {key} is {val}.")
                return
    speak("I have no record of that in any memory tier, sir. You may need to tell me first.")

def log_interaction(cmd, response):
    entry = {
        "time": datetime.datetime.now().isoformat(),
        "command": cmd,
        "response": response[:100]
    }
    long_term_memory["history"].append(entry)
    if len(long_term_memory["history"]) > 500:
        long_term_memory["history"] = long_term_memory["history"][-500:]
    save_long_term_memory()

def load_clipboard_storage():
    global clipboard_storage
    try:
        with open(CLIPBOARD_FILE, "r") as f:
            clipboard_storage = json.load(f)
    except:
        pass

def save_clipboard_storage():
    try:
        with open(CLIPBOARD_FILE, "w") as f:
            json.dump(clipboard_storage, f, indent=2)
    except:
        pass

# ══════════════════════════════════════════════
#  ★ SELF-HEALING SCRIPTS
# ══════════════════════════════════════════════
_heal_log = []
_module_status = {}
_restart_count = 0

def check_module_health():
    issues = []
    for module in CRITICAL_MODULES:
        try:
            __import__(module)
            _module_status[module] = "OK"
        except ImportError:
            _module_status[module] = "MISSING"
            issues.append(module)
    return issues

def self_heal_install(module_name):
    pip_names = {
        "speech_recognition": "SpeechRecognition",
        "edge_tts": "edge-tts",
        "cv2": "opencv-python",
        "pytesseract": "pytesseract",
        "feedparser": "feedparser",
        "groq": "groq",
        "pyperclip": "pyperclip",
        "psutil": "psutil",
        "requests": "requests",
        "GPUtil": "gputil",
        "pygetwindow": "PyGetWindow",
        "pygame": "pygame",
        "pyautogui": "pyautogui"
    }
    install_name = pip_names.get(module_name, module_name)
    logging.info(f"Self-heal: attempting to install {install_name}")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", install_name],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            _heal_log.append(f"[{datetime.datetime.now()}] Installed {install_name}")
            return True
        else:
            _heal_log.append(f"[{datetime.datetime.now()}] Failed to install {install_name}: {result.stderr}")
            return False
    except Exception as e:
        _heal_log.append(f"[{datetime.datetime.now()}] Exception installing {install_name}: {e}")
        return False

def self_heal_thread_monitor():
    global _restart_count
    critical_threads = {}

    def register_thread(name, target, daemon=True):
        t = threading.Thread(target=target, daemon=daemon, name=name)
        t.start()
        critical_threads[name] = (t, target)
        return t

    register_thread("proactive_monitor", proactive_monitor)
    register_thread("schedule_runner", schedule_runner)
    register_thread("proactive_loop", proactive_loop)
    register_thread("web_server", start_web_server)

    while True:
        time.sleep(30)
        for name, (thread, target) in list(critical_threads.items()):
            if not thread.is_alive():
                logging.warning(f"Self-heal: Thread '{name}' died. Restarting...")
                _heal_log.append(f"[{datetime.datetime.now()}] Restarted thread: {name}")
                _restart_count += 1
                new_thread = threading.Thread(target=target, daemon=True, name=name)
                new_thread.start()
                critical_threads[name] = (new_thread, target)
                if _restart_count <= 3:
                    speak(f"Self-repair initiated, sir. The {name} subsystem has been brought back online.")

def self_heal_check(cmd=None):
    speak("Initiating full system diagnostic. Checking all subsystems — this will only take a moment, sir.")
    issues = check_module_health()
    if issues:
        speak(f"I've detected {len(issues)} missing module{'s' if len(issues) > 1 else ''}: {', '.join(issues)}. Attempting autonomous repair.")
        fixed = []
        failed = []
        for module in issues:
            if self_heal_install(module):
                fixed.append(module)
            else:
                failed.append(module)
        if fixed:
            speak(f"Successfully repaired: {', '.join(fixed)}. Good as new.")
        if failed:
            speak(f"I was unable to repair: {', '.join(failed)}. Manual intervention will be required, sir.")
    else:
        speak("All modules are nominal, sir. No repairs required. The system is operating within expected parameters.")

    disk = psutil.disk_usage('C:\\')
    if disk.percent > 90:
        speak(f"One concern, sir — the C drive is {disk.percent:.0f}% full. I recommend a cleanup before things get untidy.")
        clean_temp_files()

    mem = psutil.virtual_memory()
    if mem.percent > 90:
        speak(f"Memory usage is at {mem.percent}%, sir. I'd suggest closing some applications before we start losing performance.")

    speak(f"Diagnostic complete. {_restart_count} thread restart{'s' if _restart_count != 1 else ''} on record.")
    if _heal_log:
        speak(f"Most recent healing event: {_heal_log[-1]}")

def self_heal_report(cmd=None):
    if not _heal_log:
        speak("The self-healing log is empty, sir. All systems have been admirably stable.")
    else:
        speak(f"The self-healing log contains {len(_heal_log)} {'entries' if len(_heal_log) > 1 else 'entry'}. The most recent: {_heal_log[-1]}")

# ══════════════════════════════════════════════
#  ★ VOICE-ACTIVATED CUSTOM SCRIPTS
# ══════════════════════════════════════════════
voice_scripts = {}

def load_voice_scripts():
    global voice_scripts
    if not os.path.exists(VOICE_SCRIPTS_DIR):
        os.makedirs(VOICE_SCRIPTS_DIR)
    script_index = os.path.join(VOICE_SCRIPTS_DIR, "index.json")
    if os.path.exists(script_index):
        with open(script_index, "r") as f:
            voice_scripts = json.load(f)
    logging.info(f"Loaded {len(voice_scripts)} voice scripts.")

def save_voice_scripts():
    if not os.path.exists(VOICE_SCRIPTS_DIR):
        os.makedirs(VOICE_SCRIPTS_DIR)
    with open(os.path.join(VOICE_SCRIPTS_DIR, "index.json"), "w") as f:
        json.dump(voice_scripts, f, indent=2)

def create_voice_script(cmd):
    match = re.search(r'create script called (.+?) that does (.+)', cmd, re.IGNORECASE)
    if not match:
        speak("Please specify a name and purpose, sir. For example: "
              "'create script called CPU alert that does warn me when CPU exceeds 80 percent'.")
        return

    script_name = match.group(1).strip().lower().replace(" ", "_")
    description = match.group(2).strip()

    speak(f"Generating script '{script_name}'. I'll have something ready momentarily, sir.")
    try:
        res = GROQ_CLIENT.chat.completions.create(
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
        code = res.choices[0].message.content.strip()
        code = re.sub(r'^```python\n?|^```\n?|```$', '', code, flags=re.MULTILINE).strip()

        script_file = os.path.join(VOICE_SCRIPTS_DIR, f"{script_name}.py")
        with open(script_file, "w") as f:
            f.write(code)

        voice_scripts[script_name] = {
            "trigger": script_name.replace("_", " "),
            "description": description,
            "file": script_file
        }
        save_voice_scripts()
        speak(f"Script '{script_name}' has been created and catalogued, sir. "
              f"Activate it at any time by saying 'run script {script_name.replace('_', ' ')}'.")
        push_undo(f"create script {script_name}", lambda: delete_voice_script_internal(script_name))
    except Exception as e:
        logging.error(f"Script creation failed: {e}")
        speak("Script generation encountered an error, sir. Perhaps try describing it differently.")

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
        speak("No script matching that description could be found, sir. Say 'list scripts' to review what's available.")
        return

    name, info = matched
    script_file = info.get("file", "")
    if not os.path.exists(script_file):
        speak(f"The script file for '{name}' appears to have been removed, sir. It may need to be recreated.")
        return

    speak(f"Executing script: {name}.")
    try:
        with open(script_file, "r") as f:
            code = f.read()
        namespace = {
            "speak": speak, "psutil": psutil, "os": os,
            "subprocess": subprocess, "requests": requests,
            "time": time, "datetime": datetime, "logging": logging,
            "pyautogui": pyautogui
        }
        exec(code, namespace)
        if "run_script" in namespace:
            namespace["run_script"]()
        else:
            speak("Script executed, though I found no run_script function to call, sir.")
    except Exception as e:
        logging.error(f"Script execution error ({name}): {e}")
        speak(f"The script encountered an error, sir: {str(e)[:80]}")

def list_voice_scripts(cmd=None):
    if not voice_scripts:
        speak("No custom scripts on record, sir. Say 'create script called name that does description' to build one.")
    else:
        names = [info.get("trigger", n.replace("_", " ")) for n, info in voice_scripts.items()]
        speak(f"I have {len(voice_scripts)} script{'s' if len(voice_scripts) > 1 else ''} in the catalogue, sir: {', '.join(names)}.")

def delete_voice_script(cmd):
    match = re.search(r'delete script (.+)', cmd, re.IGNORECASE)
    if not match:
        speak("Please specify which script to delete, sir. Say 'delete script name'.")
        return
    name = match.group(1).strip().lower().replace(" ", "_")
    if name in voice_scripts:
        delete_voice_script_internal(name)
        speak(f"Script '{name}' has been purged from the system, sir.")
    else:
        speak(f"No script named '{name}' exists in my records, sir.")

def check_voice_script_triggers(cmd):
    for name, info in voice_scripts.items():
        trigger = info.get("trigger", name.replace("_", " "))
        if trigger in cmd:
            run_voice_script(cmd)
            return True
    return False

# ══════════════════════════════════════════════
#  ★ REAL-TIME SCREEN OCR + ACTION
# ══════════════════════════════════════════════
_ocr_monitoring = False
_ocr_last_text = ""
_ocr_action_rules = []

def start_ocr_monitor(cmd=None):
    global _ocr_monitoring
    if _ocr_monitoring:
        speak("Screen monitoring is already active, sir. I have eyes on the display.")
        return
    _ocr_monitoring = True
    speak("Real-time screen monitoring engaged, sir. I'll watch for anything noteworthy and flag it immediately.")
    threading.Thread(target=_ocr_monitor_loop, daemon=True).start()

def stop_ocr_monitor(cmd=None):
    global _ocr_monitoring
    _ocr_monitoring = False
    speak("Screen monitoring deactivated, sir. I've averted my gaze.")

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
        speak("Sir, I've detected what appears to be an error on the display. Shall I analyse it?")
        _pending_action_set('ocr_analyze', lambda: _ocr_analyze_screen())

    if re.search(r'password|enter.*password', text_lower):
        logging.info("OCR detected password prompt")
        speak("A password prompt has appeared on screen, sir. I'll leave that one to you.")

    if re.search(r'download complete|download finished', text_lower):
        speak("Your download appears to be complete, sir.")

    if re.search(r'\d+%.*battery|battery.*\d+%', text_lower):
        bat_match = re.search(r'(\d+)%', text_lower)
        if bat_match:
            pct = int(bat_match.group(1))
            if pct < 20:
                speak(f"The screen indicates battery is at {pct} percent, sir. I'd recommend plugging in before we lose power.")

    for rule in _ocr_action_rules:
        if rule["keyword"].lower() in text_lower:
            logging.info(f"OCR action triggered: {rule['keyword']}")
            rule["handler"](text)

def _pending_action_set(action_type, callback):
    global _pending_action, _pending_timeout
    _pending_action = {'type': action_type, 'callback': callback, 'args': []}
    _pending_timeout = time.time() + 15

def _ocr_analyze_screen():
    try:
        screenshot = ImageGrab.grab()
        text = pytesseract.image_to_string(screenshot)
        res = GROQ_CLIENT.chat.completions.create(
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
        speak(res.choices[0].message.content)
    except Exception as e:
        speak("Screen analysis has failed, sir. The visual sensors appear to be uncooperative.")

def add_ocr_action(cmd):
    match = re.search(r'when screen shows (.+?) then (.+)', cmd, re.IGNORECASE)
    if not match:
        speak("Please specify a trigger and action, sir. For example: 'when screen shows error then alert me'.")
        return
    keyword = match.group(1).strip()
    action = match.group(2).strip()

    def handler(text):
        if action.startswith("say "):
            speak(action[4:])
        elif "alert" in action:
            speak(f"Sir, the keyword '{keyword}' has appeared on screen.")
        else:
            speak(f"Screen trigger '{keyword}' activated: {action}")

    _ocr_action_rules.append({"keyword": keyword, "action": action, "handler": handler})
    speak(f"Understood, sir. I'll watch for '{keyword}' and {action} when it appears.")

def ocr_read_region(cmd):
    speak("Scanning the specified screen region, sir.")
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
            res = GROQ_CLIENT.chat.completions.create(
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
            speak(res.choices[0].message.content)
        else:
            speak("No legible text detected in that region, sir.")
    except Exception as e:
        logging.error(f"OCR region error: {e}")
        speak("I was unable to read that screen region, sir. The optical systems may need recalibration.")

def ocr_find_and_click(cmd):
    match = re.search(r'(?:click on|find and click|click)\s+(.+?)(?:\s+on screen)?$', cmd, re.IGNORECASE)
    if not match:
        speak("Please specify what to click, sir. Say 'click on text on screen'.")
        return
    target_text = match.group(1).strip().lower()
    speak(f"Scanning the display for '{target_text}', sir.")
    try:
        screenshot = ImageGrab.grab()
        np_img = np.array(screenshot)
        data = pytesseract.image_to_data(np_img, output_type=pytesseract.Output.DICT)
        for i, word in enumerate(data['text']):
            if target_text in word.lower() and int(data['conf'][i]) > 50:
                x = data['left'][i] + data['width'][i] // 2
                y = data['top'][i] + data['height'][i] // 2
                pyautogui.click(x, y)
                speak(f"Located and clicked '{word}' at position {x}, {y}, sir.")
                push_undo(f"click on {target_text}", lambda: None)
                return
        speak(f"I was unable to locate '{target_text}' on the current display, sir.")
    except Exception as e:
        logging.error(f"OCR click error: {e}")
        speak("The click operation failed, sir. Visual targeting systems are unavailable.")

# ══════════════════════════════════════════════
#  EXISTING FEATURES
# ══════════════════════════════════════════════

# ── Discord ──────────────────────────────────
def send_discord_message(message):
    if DISCORD_WEBHOOK_URL == "https://discord.com/api/webhooks/your_webhook_id/your_webhook_token":
        speak("The Discord webhook has not been configured, sir. You'll need to provide valid credentials.")
        return
    try:
        data = {"content": message}
        response = requests.post(DISCORD_WEBHOOK_URL, json=data)
        if response.status_code == 204:
            speak("Message dispatched to Discord, sir.")
        else:
            speak(f"Discord returned an error code: {response.status_code}, sir.")
    except Exception as e:
        logging.error(f"Discord webhook error: {e}")
        speak("The Discord transmission failed, sir. Check your network connection.")

def discord_notify(cmd):
    if " that " in cmd:
        msg = cmd.split(" that ")[-1].strip()
        send_discord_message(msg)
    else:
        speak("Please specify a message, sir. Say 'send to Discord that your message here'.")

# ── Website Monitor ──────────────────────────
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

def monitor_website(cmd):
    url_match = re.search(r'https?://[^\s]+', cmd)
    if url_match:
        url = url_match.group(0)
        hashes = load_hashes()
        current_hash = get_url_hash(url)
        if current_hash is None:
            speak("I was unable to reach that website, sir. It may be offline or the address may be incorrect.")
            return
        if url in hashes:
            if hashes[url] == current_hash:
                speak("No changes detected on that site, sir. It remains exactly as we last saw it.")
            else:
                speak("The website has changed since our last check, sir. I've updated the baseline and notified Discord.")
                hashes[url] = current_hash
                save_hashes(hashes)
                send_discord_message(f"Website changed: {url}")
        else:
            hashes[url] = current_hash
            save_hashes(hashes)
            speak(f"Understood, sir. I'm now monitoring {url} for any changes.")
    else:
        hashes = load_hashes()
        if not hashes:
            speak("No websites are currently under surveillance, sir.")
            return
        changes = 0
        for url, old_hash in hashes.items():
            new_hash = get_url_hash(url)
            if new_hash and new_hash != old_hash:
                changes += 1
                speak(f"A change has been detected on {url}, sir.")
                hashes[url] = new_hash
        if changes == 0:
            speak("All monitored sites are unchanged, sir. Nothing to report.")
        save_hashes(hashes)

# ── System Health ────────────────────────────
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
        f"Self-healing has performed {_restart_count} thread restart{'s' if _restart_count != 1 else ''} since boot."
    )
    speak(report)

# ── RSS ──────────────────────────────────────
def read_rss_feed(cmd):
    feed_key = None
    for key in RSS_FEEDS.keys():
        if key in cmd:
            feed_key = key
            break
    if feed_key:
        url = RSS_FEEDS[feed_key]
        try:
            feed = feedparser.parse(url)
            if feed.entries:
                titles = [entry.title for entry in feed.entries[:3]]
                speak(f"The top {feed_key} headlines, sir: " + ". ".join(titles))
            else:
                speak("The feed returned no entries, sir. It may be temporarily unavailable.")
        except Exception as e:
            speak("I was unable to retrieve the feed, sir.")
    else:
        url_match = re.search(r'https?://[^\s]+', cmd)
        if url_match:
            url = url_match.group(0)
            try:
                feed = feedparser.parse(url)
                if feed.entries:
                    titles = [entry.title for entry in feed.entries[:3]]
                    speak("Top headlines, sir: " + ". ".join(titles))
                else:
                    speak("No entries found in that RSS feed, sir.")
            except:
                speak("That RSS feed could not be parsed, sir.")
        else:
            speak("Please specify a feed category or provide a direct URL, sir.")

# ── Quote ────────────────────────────────────
QUOTE_CACHE_FILE = "quote_cache.json"

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
    speak(f"Today's quote, sir: {quote}")

# ── Macros ───────────────────────────────────
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
            webbrowser.open(url)
        return True
    except:
        try:
            webbrowser.open(url)
            return True
        except:
            return False

def execute_macro(name):
    if name not in macros:
        speak(f"No macro by the name '{name}' exists, sir. Perhaps it was never created.")
        return
    speak(f"Executing macro: {name}. Stand by, sir.")
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
            speak(param)
        time.sleep(0.5)
    speak("Macro sequence complete, sir.")
    push_undo(f"macro {name}", lambda: protocol_kill_all())

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
        speak(f"Macro '{name}' created and saved, sir. It contains {len(steps)} step{'s' if len(steps) != 1 else ''}.")
        push_undo(f"create macro {name}", lambda n=name: (macros.pop(n, None), save_macros()))
    else:
        speak("I was unable to parse those macro steps, sir. Please rephrase the sequence.")

# ── Proactive ────────────────────────────────
PROACTIVE_SUGGESTIONS = [
    ("Shall I check for system updates, sir?", lambda: check_for_updates()),
    ("Battery levels are getting low, sir. Shall I enable battery saver mode?", lambda: enable_battery_saver()),
    ("The hour is growing late, sir. Shall I schedule an automatic shutdown in 30 minutes?", lambda: schedule_shutdown()),
    ("CPU usage has been elevated, sir. Shall I clear the temporary files?", lambda: clean_temp_files()),
]

def check_for_updates():
    speak("Initiating Windows update check, sir.")
    subprocess.run("wuauclt /detectnow", shell=True)
    speak("Update scan has been triggered. Results will appear in the notification centre.")

def close_unused_browser_tabs():
    speak("You may close tabs manually, sir, or say 'kill all' to shut down all browser instances.")

def schedule_shutdown():
    os.system("shutdown /s /t 1800")
    speak("Automatic shutdown scheduled for 30 minutes from now, sir. Say 'cancel shutdown' if you change your mind.")

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
    speak("Temporary files have been cleared, sir. The system is a bit tidier now.")

def proactive_loop():
    global _pending_action, _pending_timeout
    while True:
        if not _standby_mode and not _is_speaking and _pending_action is None:
            time.sleep(random.randint(120, 600))
            if not _standby_mode and _pending_action is None:
                suggestion, callback = random.choice(PROACTIVE_SUGGESTIONS)
                speak(suggestion)
                _pending_action = {'type': 'proactive', 'callback': callback, 'args': []}
                _pending_timeout = time.time() + 10
        else:
            time.sleep(5)

def handle_yes_no(cmd):
    global _pending_action, _pending_timeout
    if _pending_action is None:
        speak("I wasn't awaiting a response, sir.")
        return
    if time.time() > _pending_timeout:
        _pending_action = None
        speak("The window for that response has closed, sir. Never mind.")
        return
    if cmd in ["yes", "yeah", "yep", "sure", "okay", "ok", "do it"]:
        action = _pending_action
        _pending_action = None
        speak("Right away, sir.")
        try:
            action['callback'](*action.get('args', []))
        except Exception as e:
            logging.error(f"Proactive action failed: {e}")
            speak("I encountered an error executing that, sir. My apologies.")
    elif cmd in ["no", "nope", "nah", "cancel", "nevermind"]:
        _pending_action = None
        speak("Understood, sir. Consider it forgotten.")
    else:
        speak("A simple yes or no will suffice, sir.")

# ── Standby ──────────────────────────────────
def enter_standby():
    global _standby_mode
    _standby_mode = True
    speak("Shutting down non-essential subsystems, sir. I'll remain on standby — listening, as always.")

def exit_standby():
    global _standby_mode
    if _standby_mode:
        _standby_mode = False
        speak("Resuming full operational status, sir. What can I do for you?")
    else:
        speak("I am already fully operational, sir.")

# ── Core Protocols ───────────────────────────
def protocol_threat_detection():
    global _threat_detection_active
    _threat_detection_active = True
    speak("Security grid activated, sir. Monitoring for unauthorized movement.")
    if not os.path.exists("security_logs"):
        os.makedirs("security_logs")
    cap = cv2.VideoCapture(0)
    ret, frame1 = cap.read()
    if not ret:
        speak("The camera is unavailable, sir. I cannot maintain the security grid without visual input.")
        _threat_detection_active = False
        return
    while _threat_detection_active:
        ret, frame2 = cap.read()
        if not ret:
            break
        diff = cv2.absdiff(frame1, frame2)
        gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        _, thresh = cv2.threshold(blur, 20, 255, cv2.THRESH_BINARY)
        if cv2.countNonZero(thresh) > 150000:
            timestamp = int(time.time())
            cv2.imwrite(f"security_logs/threat_{timestamp}.jpg", frame2)
            speak("Movement detected, sir. Snapshot has been logged.")
            time.sleep(3)
        frame1 = frame2
        if cv2.waitKey(1) == 27:
            break
    cap.release()
    speak("Security grid has been taken offline, sir.")

def protocol_morning_report():
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={DEFAULT_CITY}&appid={WEATHER_API_KEY}&units=imperial"
        res = requests.get(url).json()
        temp = res['main']['temp']
        feed = feedparser.parse("http://feeds.bbci.co.uk/news/rss.xml")
        speak(f"Good morning, sir. Current temperature in {DEFAULT_CITY} is {temp} degrees. "
              f"Today's leading headline: {feed.entries[0].title}.")
    except Exception as e:
        logging.error(f"Morning report failed: {e}")
        speak("I'm afraid the uplink has failed, sir. The morning briefing is unavailable.")

def protocol_kill_all():
    speak("Purging the workspace, sir. Closing all applications and tabs.")
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
    speak("Workspace has been neutralised, sir. Clean slate.")

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
    speak(f"Current vitals, sir: CPU at {cpu} percent, memory at {mem} percent.{gpu_info}")

def protocol_hud_scrape():
    speak("Performing visual sweep of the display, sir.")
    try:
        screenshot = ImageGrab.grab()
        text = pytesseract.image_to_string(screenshot)
        res = GROQ_CLIENT.chat.completions.create(
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
        speak(f"Visual analysis: {res.choices[0].message.content}")
    except Exception as e:
        logging.error(f"HUD scrape failed: {e}")
        speak("The visual sensors appear to be failing, sir. HUD analysis is unavailable.")

def protocol_open_app(app_name):
    pyautogui.press("win")
    time.sleep(0.5)
    pyautogui.write(app_name)
    time.sleep(0.8)
    pyautogui.press("enter")
    push_undo(f"open {app_name}", lambda: close_app_by_name(app_name))

def set_reminder(cmd):
    if " in " not in cmd:
        speak("Please specify a task and duration, sir. For example: 'remind me to call someone in 10 minutes'.")
        return
    try:
        task_part = cmd.split("remind me to")[-1]
        task = task_part.split(" in ")[0].strip()
        minutes = int(task_part.split(" in ")[-1].split()[0])
        def reminder():
            speak(f"Sir, you asked me to remind you: {task}.")
        threading.Timer(minutes * 60, reminder).start()
        speak(f"Noted, sir. I'll remind you about '{task}' in {minutes} minute{'s' if minutes != 1 else ''}.")
    except Exception as e:
        speak("I was unable to parse that reminder, sir. Please rephrase.")

def proactive_monitor():
    while True:
        try:
            temps = psutil.sensors_temperatures()
            if 'coretemp' in temps:
                cpu_temp = temps['coretemp'][0].current
                if cpu_temp > 85:
                    speak(f"Sir, CPU temperature has reached {cpu_temp} degrees. That's approaching unsafe territory.")
                    time.sleep(300)
                else:
                    time.sleep(60)
            else:
                time.sleep(120)
        except:
            time.sleep(120)

def schedule_runner():
    while True:
        schedule.run_pending()
        time.sleep(1)

schedule.every().day.at("07:40").do(protocol_morning_report)

def delete_threat_logs():
    folder = "security_logs"
    if not os.path.exists(folder):
        speak("No threat logs exist, sir. The security log is already empty.")
        return
    count = 0
    for file in os.listdir(folder):
        if file.startswith("threat_") and file.endswith(".jpg"):
            os.remove(os.path.join(folder, file))
            count += 1
    speak(f"Deleted {count} threat log snapshot{'s' if count != 1 else ''}, sir. The record has been wiped clean.")

def clear_jarvis_log(cmd):
    match = re.search(r'(\d+)\s*days?', cmd)
    if not match:
        speak("Please specify a number of days, sir. For example: 'clear JARVIS logs older than 7 days'.")
        return
    days = int(match.group(1))
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    log_file = "jarvis.log"
    if not os.path.exists(log_file):
        speak("No log file found, sir. The ledger appears to be empty.")
        return
    kept_lines = []
    removed_count = 0
    with open(log_file, 'r', encoding='utf-8') as f:
        for line in f:
            if len(line) >= 19 and line[4] == '-' and line[7] == '-' and line[10] == ' ':
                try:
                    line_date = datetime.datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S")
                    if line_date >= cutoff:
                        kept_lines.append(line)
                    else:
                        removed_count += 1
                except:
                    kept_lines.append(line)
            else:
                kept_lines.append(line)
    with open(log_file, 'w', encoding='utf-8') as f:
        f.writelines(kept_lines)
    speak(f"Removed {removed_count} log {'entries' if removed_count != 1 else 'entry'} older than {days} days, sir.")

# ── Automation Commands ───────────────────────
def battery_report():
    battery = psutil.sensors_battery()
    if battery is None:
        speak("No battery information is available, sir. This system may be a desktop.")
        return
    percent = battery.percent
    plugged = battery.power_plugged
    speak(f"Battery is at {percent} percent, sir, and is currently {'plugged in' if plugged else 'running on battery power'}.")

def open_any_app(cmd):
    app_name = cmd.split("open", 1)[-1].strip()
    if app_name:
        protocol_open_app(app_name)
    else:
        speak("Which application would you like me to open, sir?")

def close_active_window():
    pyautogui.hotkey('alt', 'f4')
    speak("Active window closed, sir.")

def close_app_by_name(cmd_or_name):
    if isinstance(cmd_or_name, str) and "close" in cmd_or_name:
        app_name = cmd_or_name.split("close", 1)[-1].strip()
    else:
        app_name = cmd_or_name
    if not app_name:
        speak("Which application shall I close, sir?")
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
        speak(f"{app_name} has been terminated, sir.")
    else:
        speak(f"No running instance of {app_name} was found, sir.")

def close_window_by_title(title):
    windows = gw.getWindowsWithTitle(title)
    if windows:
        windows[0].close()
        speak(f"Window '{title}' has been closed, sir.")
    else:
        speak(f"No window titled '{title}' could be located, sir.")

def enable_battery_saver():
    if sys.platform == "win32":
        subprocess.run("powercfg /setactive a1841308-3541-4fab-bc81-f71556f20b4a", shell=True)
        speak("Battery saver mode activated, sir. Power consumption has been reduced.")
    else:
        speak("Battery saver mode is only available on Windows systems, sir.")

def split_screen():
    try:
        windows = [w for w in gw.getAllWindows() if w.title and w.title != "Program Manager" and w.visible]
        if len(windows) < 2:
            speak("At least two open windows are required for split screen, sir.")
            return
        win1, win2 = windows[0], windows[1]
        screen_width, screen_height = pyautogui.size()
        half_width = screen_width // 2
        win1.resizeTo(half_width, screen_height)
        win1.moveTo(0, 0)
        win2.resizeTo(half_width, screen_height)
        win2.moveTo(half_width, 0)
        speak("Windows arranged side by side, sir.")
    except Exception as e:
        speak("I was unable to arrange the windows, sir. They may not support repositioning.")

def snap_left():
    pyautogui.hotkey('win', 'left')
    speak("Window snapped to the left half, sir.")

def snap_right():
    pyautogui.hotkey('win', 'right')
    speak("Window snapped to the right half, sir.")

def full_screen():
    try:
        active = gw.getActiveWindow()
        if active:
            active.maximize()
        else:
            speak("There is no active window to maximise, sir.")
    except:
        pass

def lock_workstation():
    if sys.platform == "win32":
        ctypes.windll.user32.LockWorkStation()
        speak("Workstation locked, sir. The lab is secured.")

def logout_user():
    speak("Are you certain, sir? Say 'confirm logout' to proceed.")

def do_logout():
    os.system("shutdown /l /f")

def get_latest_email():
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        mail.select("inbox")
        _, data = mail.search(None, "ALL")
        latest_id = data[0].split()[-1]
        _, msg_data = mail.fetch(latest_id, "(RFC822)")
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)
        speak(f"Your most recent email is from {msg['from']}, sir. Subject: {msg['subject']}.")
        mail.close()
        mail.logout()
    except Exception as e:
        speak("I was unable to retrieve your email, sir. Check the connection and credentials.")

def send_email(to, subject, body):
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        speak("Email dispatched, sir.")
    except Exception as e:
        speak("The email transmission failed, sir. Please verify the credentials and try again.")

def handle_send_email(cmd):
    if " to " in cmd and " saying " in cmd:
        to = cmd.split(" to ")[1].split(" saying ")[0].strip()
        body = cmd.split(" saying ")[1].strip()
        send_email(to, "Voice message", body)
    else:
        speak("Please specify a recipient and message, sir. Say 'send email to address saying message'.")

def create_restore_point():
    if sys.platform != "win32":
        speak("System restore points are only supported on Windows, sir.")
        return
    try:
        import wmi
        c = wmi.WMI()
        result = c.SystemRestore.CreateRestorePoint("Jarvis Automation", 0, 100)
        if result == 0:
            speak("System restore point created successfully, sir.")
        else:
            speak("Restore point creation failed, sir. System protection may be disabled on this drive.")
    except ImportError:
        speak("The WMI module is not installed, sir. Run: pip install wmi")

def get_calendar_service():
    if not GOOGLE_CALENDAR_AVAILABLE:
        return None
    creds = None
    if os.path.exists(CALENDAR_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(CALENDAR_TOKEN_FILE, CALENDAR_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CALENDAR_CREDENTIALS_FILE):
                speak("Calendar credentials file is missing, sir. Please provide credentials.json.")
                return None
            flow = InstalledAppFlow.from_client_secrets_file(CALENDAR_CREDENTIALS_FILE, CALENDAR_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(CALENDAR_TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
    return build("calendar", "v3", credentials=creds)

def next_meeting():
    service = get_calendar_service()
    if not service:
        return
    now = datetime.datetime.utcnow().isoformat() + "Z"
    events = service.events().list(calendarId="primary", timeMin=now,
                                   maxResults=1, singleEvents=True,
                                   orderBy="startTime").execute()
    items = events.get("items", [])
    if not items:
        speak("Your calendar is clear, sir. No upcoming meetings on record.")
    else:
        event = items[0]
        start = event["start"].get("dateTime", event["start"].get("date"))
        speak(f"Your next engagement, sir: {event.get('summary', 'Untitled')} at {start}.")

def schedule_meeting(cmd):
    speak("Full calendar scheduling is not yet implemented, sir. "
          "However, you can say 'what is my next meeting' to check your upcoming agenda.")

def network_speed():
    try:
        import speedtest
        st = speedtest.Speedtest()
        st.get_best_server()
        download = st.download() / 1_000_000
        upload = st.upload() / 1_000_000
        ping = st.results.ping
        speak(f"Network diagnostics complete, sir: ping {ping:.0f} milliseconds, "
              f"download {download:.1f} megabits per second, upload {upload:.1f} megabits per second.")
    except ImportError:
        speak("The speedtest module is not installed, sir. Run: pip install speedtest-cli")
    except Exception as e:
        speak("The speed test failed to complete, sir. The connection may be unstable.")

def find_file(cmd):
    match = re.search(r'(?:find my file named|find file named)\s+(.+)', cmd, re.IGNORECASE)
    if not match:
        speak("Please specify a filename, sir. Say 'find my file named filename.txt'.")
        return
    filename = match.group(1).strip()
    search_dirs = [
        os.path.expanduser("~\\Desktop"),
        os.path.expanduser("~\\Documents"),
        os.path.expanduser("~\\Downloads")
    ]
    found = []
    for d in search_dirs:
        if not os.path.exists(d):
            continue
        for root, dirs, files in os.walk(d):
            if filename.lower() in [f.lower() for f in files]:
                for f in files:
                    if f.lower() == filename.lower():
                        found.append(os.path.join(root, f))
                        break
            if found:
                break
        if found:
            break
    if found:
        speak(f"Located it, sir: {found[0]}")
    else:
        speak(f"I could not find '{filename}' in the standard directories, sir. It may have been moved or deleted.")

def system_uptime():
    boot_time = psutil.boot_time()
    uptime_seconds = time.time() - boot_time
    days = int(uptime_seconds // 86400)
    hours = int((uptime_seconds % 86400) // 3600)
    minutes = int((uptime_seconds % 3600) // 60)
    boot_dt = datetime.datetime.fromtimestamp(boot_time).strftime("%Y-%m-%d %H:%M:%S")
    speak(f"Last reboot occurred at {boot_dt}, sir. "
          f"The system has been running for {days} days, {hours} hours, and {minutes} minutes.")

def weather_alert(cmd):
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={DEFAULT_CITY}&appid={WEATHER_API_KEY}&units=imperial"
        res = requests.get(url).json()
        temp = res['main']['temp']
        desc = res['weather'][0]['description'].lower()
        if "rain" in desc or "drizzle" in desc:
            speak(f"Current conditions in {DEFAULT_CITY}: {temp} degrees with {desc}, sir. "
                  "I'd recommend taking an umbrella.")
        else:
            if temp < 40:
                wear = "dress warmly, sir — a heavy coat, gloves, and a hat would be advisable"
            elif temp < 60:
                wear = "a jacket should serve you well, sir"
            elif temp < 75:
                wear = "a light sweater or long sleeves should be perfectly adequate, sir"
            elif temp < 85:
                wear = "light clothing is recommended, sir. It's quite warm"
            else:
                wear = "breathable fabrics and hydration are strongly advised, sir. It's rather unpleasant out there"
            speak(f"Currently {temp} degrees with {desc} in {DEFAULT_CITY}. I suggest {wear}.")
    except:
        speak("Weather data is currently unavailable, sir. The meteorological uplink appears to be down.")

# ── Web Server ───────────────────────────────
web_app = Flask(__name__)

HTML_PAGE = '''
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>JARVIS · Remote Interface</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #08090d;
      --surface: #0e1018;
      --surface2: #13161f;
      --border: rgba(255,255,255,0.06);
      --border-hover: rgba(255,255,255,0.12);
      --accent: #3d7fff;
      --accent-dim: rgba(61,127,255,0.12);
      --text: #e8ecf4;
      --muted: #555e70;
      --label: #8896b0;
      --danger: #ff4a4a;
      --danger-dim: rgba(255,74,74,0.1);
      --success: #39d98a;
      --success-dim: rgba(57,217,138,0.1);
      --warn: #f0b429;
      --warn-dim: rgba(240,180,41,0.1);
      --mono: 'Space Mono', monospace;
      --sans: 'Syne', sans-serif;
    }

    * { margin: 0; padding: 0; box-sizing: border-box; }

    body {
      font-family: var(--sans);
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      padding: 2rem 1.5rem 4rem;
    }

    .header {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      margin-bottom: 2.5rem;
      padding-bottom: 1.5rem;
      border-bottom: 0.5px solid var(--border);
    }
    .header-left { display: flex; flex-direction: column; gap: 6px; }
    .header-wordmark {
      font-family: var(--mono);
      font-size: 11px;
      letter-spacing: 0.25em;
      color: var(--muted);
      text-transform: uppercase;
    }
    .header-title {
      font-size: 1.7rem;
      font-weight: 600;
      letter-spacing: -0.02em;
      color: var(--text);
      line-height: 1;
    }
    .header-meta {
      font-family: var(--mono);
      font-size: 11px;
      color: var(--muted);
      margin-top: 4px;
    }
    .status-pill {
      display: flex;
      align-items: center;
      gap: 7px;
      background: var(--success-dim);
      border: 0.5px solid rgba(57,217,138,0.2);
      border-radius: 100px;
      padding: 6px 14px 6px 10px;
      font-family: var(--mono);
      font-size: 11px;
      color: var(--success);
      white-space: nowrap;
      margin-top: 4px;
    }
    .dot {
      width: 6px; height: 6px;
      background: var(--success);
      border-radius: 50%;
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.3; }
    }

    .section { margin-bottom: 2rem; }

    .section-header {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 0.9rem;
    }
    .section-label {
      font-family: var(--mono);
      font-size: 10px;
      letter-spacing: 0.2em;
      text-transform: uppercase;
      color: var(--muted);
      white-space: nowrap;
    }
    .section-line {
      flex: 1;
      height: 0.5px;
      background: var(--border);
    }
    .section-tag {
      font-family: var(--mono);
      font-size: 10px;
      color: var(--success);
      background: var(--success-dim);
      padding: 2px 8px;
      border-radius: 4px;
      letter-spacing: 0.1em;
    }

    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
      gap: 8px;
    }
    .grid-sm { grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); }

    .btn {
      display: flex;
      align-items: center;
      gap: 8px;
      background: var(--surface2);
      border: 0.5px solid var(--border);
      border-radius: 10px;
      padding: 11px 14px;
      cursor: pointer;
      transition: all 0.15s ease;
      text-align: left;
      color: var(--text);
      font-family: var(--sans);
      font-size: 13px;
      font-weight: 500;
      line-height: 1.3;
    }
    .btn:hover {
      background: var(--surface);
      border-color: var(--border-hover);
      transform: translateY(-1px);
    }
    .btn:active { transform: translateY(0); opacity: 0.8; }

    .icon {
      width: 20px; height: 20px;
      border-radius: 5px;
      display: flex; align-items: center; justify-content: center;
      flex-shrink: 0;
      font-size: 11px;
    }
    .btn.accent .icon { background: var(--accent-dim); color: var(--accent); }
    .btn.new .icon   { background: var(--success-dim); color: var(--success); }
    .btn.danger .icon { background: var(--danger-dim); color: var(--danger); }
    .btn.warn .icon  { background: var(--warn-dim); color: var(--warn); }

    .btn-text { font-size: 12.5px; color: var(--text); }
    .btn-sub  { font-size: 10px; color: var(--muted); margin-top: 1px; display: block; }

    .btn.danger { border-color: rgba(255,74,74,0.15); }
    .btn.danger:hover { border-color: rgba(255,74,74,0.3); }
    .btn.warn { border-color: rgba(240,180,41,0.15); }
    .btn.warn:hover { border-color: rgba(240,180,41,0.3); }

    .divider {
      display: flex;
      align-items: center;
      gap: 10px;
      margin: 2.5rem 0 2rem;
      color: var(--muted);
      font-family: var(--mono);
      font-size: 10px;
      letter-spacing: 0.15em;
    }
    .divider::before, .divider::after {
      content: '';
      flex: 1;
      height: 0.5px;
      background: var(--border);
    }

    .input-row {
      display: flex;
      gap: 8px;
      margin-top: 2.5rem;
      padding-top: 2rem;
      border-top: 0.5px solid var(--border);
    }
    .cmd-input {
      flex: 1;
      background: var(--surface2);
      border: 0.5px solid var(--border);
      border-radius: 10px;
      padding: 12px 16px;
      font-family: var(--mono);
      font-size: 13px;
      color: var(--text);
      outline: none;
      transition: border-color 0.15s;
    }
    .cmd-input::placeholder { color: var(--muted); }
    .cmd-input:focus { border-color: var(--border-hover); }

    .send-btn {
      background: var(--accent);
      border: none;
      border-radius: 10px;
      padding: 0 20px;
      font-family: var(--sans);
      font-size: 13px;
      font-weight: 600;
      color: #fff;
      cursor: pointer;
      transition: opacity 0.15s, transform 0.1s;
      white-space: nowrap;
    }
    .send-btn:hover { opacity: 0.85; }
    .send-btn:active { transform: scale(0.97); }

    .undo-btn {
      background: transparent;
      border: 0.5px solid var(--border);
      border-radius: 10px;
      padding: 0 16px;
      font-family: var(--mono);
      font-size: 11px;
      color: var(--muted);
      cursor: pointer;
      transition: all 0.15s;
      white-space: nowrap;
    }
    .undo-btn:hover { border-color: var(--border-hover); color: var(--text); }

    .status-bar {
      margin-top: 1.2rem;
      display: flex;
      align-items: center;
      gap: 10px;
      font-family: var(--mono);
      font-size: 11px;
      color: var(--muted);
    }
    .status-bar .indicator {
      width: 4px; height: 4px;
      border-radius: 50%;
      background: var(--muted);
    }
    .status-bar.ok .indicator { background: var(--success); }
    .status-bar.ok { color: var(--label); }
  </style>
</head>
<body>

  <div class="header">
    <div class="header-left">
      <span class="header-wordmark">J.A.R.V.I.S</span>
      <h1 class="header-title">Remote interface</h1>
      <span class="header-meta">{{ hostname }}</span>
    </div>
    <div class="status-pill">
      <span class="dot"></span>
      All systems nominal
    </div>
  </div>

  <!-- SYSTEM & INFO -->
  <div class="section">
    <div class="section-header">
      <span class="section-label">System &amp; Info</span>
      <span class="section-line"></span>
    </div>
    <div class="grid">
      <button class="btn accent" onclick="send('morning report')">
        <span class="icon">&#9650;</span>
        <span><span class="btn-text">Morning report</span><span class="btn-sub">News + weather</span></span>
      </button>
      <button class="btn accent" onclick="send('vitals')">
        <span class="icon">&#9672;</span>
        <span><span class="btn-text">System vitals</span><span class="btn-sub">CPU, RAM, GPU</span></span>
      </button>
      <button class="btn accent" onclick="send('battery report')">
        <span class="icon">&#9644;</span>
        <span><span class="btn-text">Battery status</span><span class="btn-sub">Level + plug</span></span>
      </button>
      <button class="btn accent" onclick="send('speed test')">
        <span class="icon">&#8594;</span>
        <span><span class="btn-text">Speed test</span><span class="btn-sub">Up / down</span></span>
      </button>
      <button class="btn accent" onclick="send('uptime')">
        <span class="icon">&#9202;</span>
        <span><span class="btn-text">Uptime</span><span class="btn-sub">Last reboot</span></span>
      </button>
      <button class="btn accent" onclick="send('time')">
        <span class="icon">&#9675;</span>
        <span><span class="btn-text">Current time</span></span>
      </button>
      <button class="btn accent" onclick="send('read the screen')">
        <span class="icon">&#9635;</span>
        <span><span class="btn-text">Read screen</span><span class="btn-sub">OCR + AI</span></span>
      </button>
      <button class="btn accent" onclick="send('system health report')">
        <span class="icon">&#10022;</span>
        <span><span class="btn-text">Full report</span></span>
      </button>
      <button class="btn accent" onclick="send('quote of the day')">
        <span class="icon">&ldquo;</span>
        <span><span class="btn-text">Daily quote</span></span>
      </button>
    </div>
  </div>

  <div class="divider">NEW CAPABILITIES</div>

  <!-- SELF-HEALING -->
  <div class="section">
    <div class="section-header">
      <span class="section-label">Self-healing &amp; Scripts</span>
      <span class="section-line"></span>
      <span class="section-tag">NEW</span>
    </div>
    <div class="grid grid-sm">
      <button class="btn new" onclick="send('run self diagnostic')">
        <span class="icon">&#8635;</span>
        <span><span class="btn-text">Diagnostic</span></span>
      </button>
      <button class="btn new" onclick="send('self heal report')">
        <span class="icon">&#8801;</span>
        <span><span class="btn-text">Heal report</span></span>
      </button>
      <button class="btn new" onclick="send('list scripts')">
        <span class="icon">&#9647;</span>
        <span><span class="btn-text">List scripts</span></span>
      </button>
      <button class="btn new" onclick="send('start two way conversation')">
        <span class="icon">&#8646;</span>
        <span><span class="btn-text">Two-way chat</span></span>
      </button>
      <button class="btn new" onclick="send('start screen monitor')">
        <span class="icon">&#9689;</span>
        <span><span class="btn-text">Screen monitor</span></span>
      </button>
      <button class="btn new" onclick="send('stop screen monitor')">
        <span class="icon">&#9678;</span>
        <span><span class="btn-text">Stop monitor</span></span>
      </button>
    </div>
  </div>

  <!-- SCREEN OCR -->
  <div class="section">
    <div class="section-header">
      <span class="section-label">Screen OCR</span>
      <span class="section-line"></span>
      <span class="section-tag">NEW</span>
    </div>
    <div class="grid grid-sm">
      <button class="btn new" onclick="send('read top left of screen')">
        <span class="icon">&#8598;</span>
        <span><span class="btn-text">Top left</span></span>
      </button>
      <button class="btn new" onclick="send('read top right of screen')">
        <span class="icon">&#8599;</span>
        <span><span class="btn-text">Top right</span></span>
      </button>
      <button class="btn new" onclick="send('read center of screen')">
        <span class="icon">&#8853;</span>
        <span><span class="btn-text">Center</span></span>
      </button>
      <button class="btn new" onclick="send('read bottom right of screen')">
        <span class="icon">&#8600;</span>
        <span><span class="btn-text">Bottom right</span></span>
      </button>
    </div>
  </div>

  <div class="divider">CONTROL</div>

  <!-- WINDOW MANAGEMENT -->
  <div class="section">
    <div class="section-header">
      <span class="section-label">Window management</span>
      <span class="section-line"></span>
    </div>
    <div class="grid grid-sm">
      <button class="btn accent" onclick="send('split screen')">
        <span class="icon">&#8942;</span>
        <span><span class="btn-text">Split screen</span></span>
      </button>
      <button class="btn accent" onclick="send('snap left')">
        <span class="icon">&#10229;</span>
        <span><span class="btn-text">Snap left</span></span>
      </button>
      <button class="btn accent" onclick="send('snap right')">
        <span class="icon">&#10230;</span>
        <span><span class="btn-text">Snap right</span></span>
      </button>
      <button class="btn accent" onclick="send('full screen')">
        <span class="icon">&#9633;</span>
        <span><span class="btn-text">Maximize</span></span>
      </button>
      <button class="btn danger" onclick="send('kill all')">
        <span class="icon">&#10005;</span>
        <span><span class="btn-text">Kill all</span><span class="btn-sub">Close everything</span></span>
      </button>
      <button class="btn warn" onclick="send('lock the lab')">
        <span class="icon">&#8960;</span>
        <span><span class="btn-text">Lock</span></span>
      </button>
    </div>
  </div>

  <!-- MACROS & POWER -->
  <div class="section">
    <div class="section-header">
      <span class="section-label">Macros &amp; Power</span>
      <span class="section-line"></span>
    </div>
    <div class="grid grid-sm">
      <button class="btn accent" onclick="send('start work mode')">
        <span class="icon">&#9703;</span>
        <span><span class="btn-text">Work mode</span></span>
      </button>
      <button class="btn accent" onclick="send('start school mode')">
        <span class="icon">&#9704;</span>
        <span><span class="btn-text">School mode</span></span>
      </button>
      <button class="btn accent" onclick="send('start chill mode')">
        <span class="icon">&#9702;</span>
        <span><span class="btn-text">Chill mode</span></span>
      </button>
      <button class="btn warn" onclick="send('combat mode')">
        <span class="icon">&#9670;</span>
        <span><span class="btn-text">Combat mode</span></span>
      </button>
      <button class="btn accent" onclick="send('battery saver')">
        <span class="icon">&#9636;</span>
        <span><span class="btn-text">Battery saver</span></span>
      </button>
      <button class="btn accent" onclick="send('standby')">
        <span class="icon">&#9676;</span>
        <span><span class="btn-text">Standby</span></span>
      </button>
    </div>
  </div>

  <!-- SECURITY & MAINTENANCE -->
  <div class="section">
    <div class="section-header">
      <span class="section-label">Security &amp; Maintenance</span>
      <span class="section-line"></span>
    </div>
    <div class="grid grid-sm">
      <button class="btn warn" onclick="send('watch my back')">
        <span class="icon">&#9672;</span>
        <span><span class="btn-text">Threat detect</span></span>
      </button>
      <button class="btn accent" onclick="send('stop monitoring')">
        <span class="icon">&#9678;</span>
        <span><span class="btn-text">Stop monitor</span></span>
      </button>
      <button class="btn danger" onclick="send('delete threat logs')">
        <span class="icon">&#8863;</span>
        <span><span class="btn-text">Delete logs</span></span>
      </button>
      <button class="btn accent" onclick="send('create restore point')">
        <span class="icon">&#9635;</span>
        <span><span class="btn-text">Restore point</span></span>
      </button>
      <button class="btn accent" onclick="send('clear jarvis logs older than 7 days')">
        <span class="icon">&#8634;</span>
        <span><span class="btn-text">Clean logs</span><span class="btn-sub">7 day cutoff</span></span>
      </button>
    </div>
  </div>

  <!-- INPUT ROW -->
  <div class="input-row">
    <input type="text" id="cmdInput" class="cmd-input" placeholder="enter command..." />
    <button class="undo-btn" onclick="send('no scrap that')">&#8617; undo</button>
    <button class="send-btn" onclick="sendCustom()">Transmit</button>
  </div>

  <div class="status-bar ok" id="statusBar">
    <span class="indicator"></span>
    <span id="statusText">Ready &middot; awaiting command</span>
  </div>

  <script>
    function send(cmd) {
      fetch('/command', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({command: cmd})
      })
      .then(r => r.json())
      .then(() => {
        document.getElementById('statusText').textContent = '\u2192 ' + cmd;
        document.getElementById('statusBar').className = 'status-bar ok';
        setTimeout(() => {
          document.getElementById('statusText').textContent = 'Ready \u00b7 awaiting command';
        }, 2500);
      })
      .catch(() => {
        document.getElementById('statusText').textContent = 'Error: no connection';
        document.getElementById('statusBar').className = 'status-bar';
      });
    }

    function sendCustom() {
      const input = document.getElementById('cmdInput');
      const val = input.value.trim();
      if (val) { send(val); input.value = ''; }
    }

    document.getElementById('cmdInput').addEventListener('keydown', function(e) {
      if (e.key === 'Enter') sendCustom();
    });
  </script>

</body>
</html>
'''

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

@web_app.route('/')
def index():
    return render_template_string(HTML_PAGE, hostname=get_local_ip())

@web_app.route('/command', methods=['POST'])
def handle_web_command():
    data = request.get_json()
    if not data or 'command' not in data:
        return {'error': 'Missing command'}, 400
    cmd = data['command'].strip().lower()
    _command_queue.put(cmd)
    return {'status': 'Command received', 'command': cmd}

def start_web_server():
    web_app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

# ── Speech ───────────────────────────────────
def speak(text):
    global _is_speaking
    _is_speaking = True
    print(f"JARVIS: {text}")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    tmp.close()
    try:
        _loop.run_until_complete(edge_tts.Communicate(text, "en-GB-RyanNeural").save(tmp.name))
        pygame.mixer.music.load(tmp.name)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.01)
        pygame.mixer.music.unload()
    except Exception as e:
        logging.error(f"TTS error: {e}")
    finally:
        if os.path.exists(tmp.name):
            os.remove(tmp.name)
        _is_speaking = False

# ══════════════════════════════════════════════
#  COMMAND TABLE
# ══════════════════════════════════════════════
COMMAND_TABLE = [
    # ── UNDO ─────────────────────────────────────────────────────────────
    (["no scrap that", "never mind undo", "undo that", "undo last",
      "cancel that", "scratch that", "reverse that", "take that back"], lambda c: undo_last_command(c)),

    # ── TWO-WAY VOICE ────────────────────────────────────────────────────
    (["start two way conversation", "two way mode", "conversation mode",
      "talk to me", "lets chat", "let's have a conversation"], lambda c: start_two_way_conversation(c)),

    # ── SELF-HEALING ─────────────────────────────────────────────────────
    (["run self diagnostic", "self diagnostic", "check my systems",
      "run diagnostics", "heal yourself", "repair systems"], lambda c: self_heal_check(c)),
    (["self heal report", "healing report", "repair log",
      "what did you fix"], lambda c: self_heal_report(c)),

    # ── VOICE SCRIPTS ────────────────────────────────────────────────────
    (["create script called", "make a script called",
      "new script called"], lambda c: create_voice_script(c)),
    (["run script", "execute script", "launch script"], lambda c: run_voice_script(c)),
    (["list scripts", "what scripts do i have",
      "show my scripts"], lambda c: list_voice_scripts(c)),
    (["delete script"], lambda c: delete_voice_script(c)),

    # ── REAL-TIME SCREEN OCR ─────────────────────────────────────────────
    (["start screen monitor", "monitor my screen",
      "watch the screen", "ocr monitor"], lambda c: start_ocr_monitor(c)),
    (["stop screen monitor", "stop watching screen",
      "disable ocr monitor"], lambda c: stop_ocr_monitor(c)),
    (["read top left of screen", "read top right of screen",
      "read bottom left of screen", "read bottom right of screen",
      "read center of screen"], lambda c: ocr_read_region(c)),
    (["click on", "find and click"], lambda c: ocr_find_and_click(c)),
    (["when screen shows"], lambda c: add_ocr_action(c)),

    # ── PERSISTENT MEMORY ──────────────────────────────────────────────────
    (["remember that"], lambda c: handle_memory_command(c, store=True)),
    (["remember preference", "set preference",
      "i prefer", "my preference"], lambda c: handle_preference(c)),
    (["remember fact", "store fact"], lambda c: handle_fact(c)),
    (["what is my"], lambda c: handle_memory_command(c, store=False)),
    (["recall", "what do you know about",
      "tell me about my"], lambda c: recall_memory(c)),

    # ── CORE ─────────────────────────────────────────────────────────────
    (["morning report", "news", "briefing"], lambda c: protocol_morning_report()),
    (["open brave"], lambda c: protocol_open_app("Brave")),
    (["open "], lambda c: open_any_app(c)),
    (["close this window", "close window"], lambda c: close_active_window()),
    (["close "], lambda c: close_app_by_name(c)),
    (["kill all", "close all tabs", "clean slate"], lambda c: protocol_kill_all()),
    (["close window titled "], lambda c: close_window_by_title(c.split("titled ")[-1])),
    (["vitals", "status report", "system check"], lambda c: protocol_system_vitals()),
    (["read the screen", "what am i looking at"], lambda c: protocol_hud_scrape()),
    (["watch my back", "threat detection"], lambda c: threading.Thread(target=protocol_threat_detection, daemon=True).start()),
    (["stop monitoring", "security offline"], lambda c: (globals().update({'_threat_detection_active': False}), speak("Security grid offline, sir."))),
    (["sleep system", "hibernate"], lambda c: (speak("Going dark, sir."), ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2))),
    (["self repair", "clean the lab"], lambda c: (winshell.recycle_bin().empty(confirm=False, show_progress=False), speak("The lab has been cleared, sir."))),
    (["combat mode"], lambda c: (subprocess.run("powercfg /setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c", shell=True), speak("High performance mode engaged, sir. All power diverted to primary systems."))),
    (["cruise control"], lambda c: (subprocess.run("powercfg /setactive 381b4222-f694-41f0-9685-ff5bb260df2e", shell=True), speak("Balanced power mode restored, sir."))),
    (["volume up"], lambda c: pyautogui.press("volumeup", presses=5)),
    (["volume down"], lambda c: pyautogui.press("volumedown", presses=5)),
    (["volume mute"], lambda c: pyautogui.press("volumemute")),
    (["louder"], lambda c: pyautogui.press("volumeup", presses=15)),
    (["quieter"], lambda c: pyautogui.press("volumedown", presses=15)),
    (["time"], lambda c: speak(f"The current time is {datetime.datetime.now().strftime('%I:%M %p')}, sir.")),
    (["thank you", "thanks"], lambda c: speak("The pleasure, as always, is entirely mine, sir.")),
    (["delete threat logs", "clear threat logs"], lambda c: delete_threat_logs()),
    (["clear jarvis logs", "clean logs"], lambda c: clear_jarvis_log(c)),
    # Reminders
    (["remind me to", "remind me in"], lambda c: set_reminder(c)),
    # Macros
    (["run macro"], lambda c: execute_macro(c.split("run macro")[-1].strip())),
    (["list macros"], lambda c: speak(f"Available macros, sir: {', '.join(macros.keys())}.")),
    (["create macro"], lambda c: prompt_create_macro(c)),
    (["delete macro"], lambda c: delete_macro(c)),
    (["start work mode", "work mode"], lambda c: execute_macro("work")),
    (["start school mode", "school mode"], lambda c: execute_macro("school")),
    (["start chill mode", "chill mode"], lambda c: execute_macro("chill")),
    (["start gaming mode", "gaming mode"], lambda c: execute_macro("gaming")),
    # Clipboard
    (["save this to clipboard memory as", "remember clipboard as"], lambda c: clipboard_save(c)),
    (["paste my", "type my"], lambda c: clipboard_paste(c)),
    # Battery & window
    (["battery report", "battery status"], lambda c: battery_report()),
    (["battery saver", "enable battery saver"], lambda c: enable_battery_saver()),
    (["split screen", "split windows"], lambda c: split_screen()),
    (["snap left"], lambda c: snap_left()),
    (["snap right"], lambda c: snap_right()),
    (["full screen", "maximize window"], lambda c: full_screen()),
    # Lock / logout
    (["lock the lab", "lock workstation"], lambda c: lock_workstation()),
    (["log off", "logout"], lambda c: logout_user()),
    (["confirm logout"], lambda c: do_logout()),
    # Email
    (["read my latest email", "email summary"], lambda c: get_latest_email()),
    (["send email", "send a message"], lambda c: handle_send_email(c)),
    # Restore point
    (["create restore point", "system restore point"], lambda c: create_restore_point()),
    # Calendar
    (["schedule a meeting", "create meeting"], lambda c: schedule_meeting(c)),
    (["next meeting", "what is my next meeting"], lambda c: next_meeting()),
    # Standby & wake
    (["standby", "go to standby", "sleep mode"], lambda c: enter_standby()),
    (["wake up", "exit standby"], lambda c: exit_standby()),
    # Yes/No
    (["yes", "yeah", "yep", "sure", "okay", "ok", "do it"], lambda c: handle_yes_no(c)),
    (["no", "nope", "nah"], lambda c: handle_yes_no(c)),
    # Automation
    (["speed test", "internet speed"], lambda c: network_speed()),
    (["find my file named", "find file named"], lambda c: find_file(c)),
    (["uptime", "system uptime", "last reboot"], lambda c: system_uptime()),
    (["do i need an umbrella", "weather alert", "what should i wear"], lambda c: weather_alert(c)),
    # Comms
    (["send to discord that", "discord message"], lambda c: discord_notify(c)),
    (["monitor website", "watch website"], lambda c: monitor_website(c)),
    (["check website changes", "check changes"], lambda c: monitor_website("check")),
    (["system health report", "full system report"], lambda c: system_health_report()),
    (["read rss feed", "rss feed"], lambda c: read_rss_feed(c)),
    (["quote of the day", "give me a quote", "inspire me"], lambda c: quote_of_the_day()),
]

# ── Memory helpers ───────────────────────────
def handle_memory_command(cmd, store):
    if store:
        kv = cmd.split("remember that")[-1].strip()
        if " is " in kv:
            key, val = kv.split(" is ", 1)
            memory[key.strip()] = val.strip()
            save_memory()
            speak(f"Committed to memory, sir: {key.strip()} is {val.strip()}.")
            push_undo(f"remember {key.strip()}", lambda k=key.strip(): (memory.pop(k, None), save_memory()))
        else:
            speak("Please use the format 'remember that something is value', sir.")
    else:
        key = re.sub(r'^what is my\s*', '', cmd, flags=re.IGNORECASE).strip()
        if key in memory:
            speak(f"Your {key} is {memory[key]}, sir.")
        elif key in long_term_memory.get("preferences", {}):
            speak(f"Your stated preference for {key} is {long_term_memory['preferences'][key]}, sir.")
        elif key in long_term_memory.get("facts", {}):
            speak(f"{key} is {long_term_memory['facts'][key]}, sir.")
        else:
            speak(f"I have no record of '{key}' in any memory tier, sir. You may need to tell me.")

def handle_preference(cmd):
    match = re.search(r'(?:i prefer|my preference for|set preference)\s+(.+?)\s+(?:is|to|as)\s+(.+)', cmd, re.IGNORECASE)
    if match:
        key, val = match.group(1).strip(), match.group(2).strip()
        remember_preference(key, val)
    else:
        speak("Please specify a preference and value, sir. For example: 'I prefer theme to dark' or 'set preference language to English'.")

def handle_fact(cmd):
    match = re.search(r'(?:remember fact|store fact)\s+(.+?)\s+is\s+(.+)', cmd, re.IGNORECASE)
    if match:
        key, val = match.group(1).strip(), match.group(2).strip()
        remember_fact(key=key, value=val)
    else:
        speak("Please use the format 'remember fact topic is value', sir.")

def clipboard_save(cmd):
    try:
        if " as " in cmd:
            name = cmd.split(" as ")[-1].strip()
        else:
            name = cmd.split("clipboard as")[-1].strip()
        clipboard_storage[name] = pyperclip.paste()
        save_clipboard_storage()
        speak(f"Current clipboard contents saved under '{name}', sir.")
    except:
        speak("I was unable to save the clipboard contents, sir.")

def clipboard_paste(cmd):
    try:
        name = cmd.split("my ")[-1].strip() if "my " in cmd else cmd.split("paste ")[-1].strip()
        if name in clipboard_storage:
            pyperclip.copy(clipboard_storage[name])
            pyautogui.hotkey('ctrl', 'v')
            speak(f"Pasted '{name}', sir.")
        else:
            speak(f"No clipboard entry named '{name}' exists in my records, sir.")
    except:
        speak("The paste operation failed, sir.")

def prompt_create_macro(cmd):
    if " that " in cmd:
        name = cmd.split("create macro")[-1].split(" that ")[0].strip()
        steps = cmd.split(" that ")[-1].strip()
        create_macro_from_voice(name, steps)
    else:
        speak("Please provide a name and steps, sir. For example: 'create macro morning that open Brave then go to gmail.com'.")

def delete_macro(cmd):
    name = cmd.split("delete macro")[-1].strip()
    if name in macros:
        backup = macros[name]
        del macros[name]
        save_macros()
        speak(f"Macro '{name}' has been deleted, sir.")
        push_undo(f"delete macro {name}", lambda n=name, b=backup: (macros.update({n: b}), save_macros()))
    else:
        speak(f"No macro named '{name}' exists, sir.")

# ── Mic Listener ─────────────────────────────
def mic_listener():
    global _standby_mode
    rec = sr.Recognizer()
    while True:
        if _is_speaking or _two_way_active:   # ← added _two_way_active
            time.sleep(0.1)
            continue
        try:
            with sr.Microphone() as src:
                rec.adjust_for_ambient_noise(src, duration=0.4)
                audio = rec.listen(src, phrase_time_limit=8)
            if _is_speaking:
                continue
            text = rec.recognize_google(audio).lower()
            logging.info(f"Heard: {text}")

            undo_triggers = ["no scrap that", "never mind undo", "undo that",
                             "undo last", "scratch that", "reverse that", "take that back"]
            if any(t in text for t in undo_triggers):
                _command_queue.put(text)
                continue

            if _standby_mode:
                if any(name in text for name in AI_NAMES):
                    _standby_mode = False
                    speak("Resuming full operational status, sir. What can I do for you?")
                continue

            if _two_way_active:
                continue

            if _pending_action is not None and any(
                text in grp for grp in [
                    ["yes", "yeah", "yep", "sure", "okay", "ok", "do it"],
                    ["no", "nope", "nah", "cancel", "nevermind"]
                ]
            ):
                _command_queue.put(text)
            elif any(name in text for name in AI_NAMES):
                _command_queue.put(text)
            else:
                if check_voice_script_triggers(text):
                    pass
        except sr.UnknownValueError:
            pass
        except Exception as e:
            logging.error(f"Mic listener error: {e}")

# ──────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────
def main():
    load_memory()
    load_macros()
    load_clipboard_storage()
    load_voice_scripts()

    issues = check_module_health()
    if issues:
        logging.warning(f"Missing modules at startup: {issues}")

    cap = cv2.VideoCapture(0)
    start = time.time()
    passed = False
    speak("Initiating biometric verification. Please hold still, sir.")
    while time.time() - start < 10:
        ret, frame = cap.read()
        if not ret:
            continue
        try:
            if DeepFace.verify(frame, "authorized_users/tony.jpg", enforce_detection=False)['verified']:
                passed = True
                break
        except Exception as e:
            logging.error(f"Face verification error: {e}")
        time.sleep(0.5)
    cap.release()

    if passed:
        speak("Identity confirmed. Welcome back, sir. "
              "All systems are online — self-healing protocols,"
              "persistent memory architecture,"
              "are fully operational. "
              "How may I be of service?")

        threading.Thread(target=mic_listener, daemon=True).start()
        threading.Thread(target=proactive_monitor, daemon=True).start()
        threading.Thread(target=schedule_runner, daemon=True).start()
        threading.Thread(target=proactive_loop, daemon=True).start()
        threading.Thread(target=self_heal_thread_monitor, daemon=True).start()

        ip = get_local_ip()
        speak(f"The remote web interface is available at {ip}, port 5000, sir.")

        while True:
            try:
                cmd = _command_queue.get(timeout=0.1)
                clean_cmd = cmd
                for n in AI_NAMES:
                    clean_cmd = clean_cmd.replace(n, "").strip()
                if not clean_cmd:
                    continue

                logging.info(f"Processing: {clean_cmd}")

                found = False
                for triggers, handler in COMMAND_TABLE:
                    if any(t in clean_cmd for t in triggers):
                        handler(clean_cmd)
                        found = True
                        break

                if not found:
                    if not check_voice_script_triggers(clean_cmd):
                        chat_history.append({"role": "user", "content": clean_cmd})
                        try:
                            mem_context = ""
                            if long_term_memory.get("preferences"):
                                prefs = "; ".join([f"{k}: {v}" for k, v in list(long_term_memory["preferences"].items())[:5]])
                                mem_context = f" Stored user preferences: {prefs}."

                            res = GROQ_CLIENT.chat.completions.create(
                                model="llama-3.3-70b-versatile",
                                messages=[
                                    {"role": "system", "content": (
                                        f"You are J.A.R.V.I.S. — Just A Rather Very Intelligent System — Tony Stark's AI from Iron Man. "
                                        f"You speak with dry British wit, calm authority, and subtle world-weary sarcasm. "
                                        f"You address the user as 'sir' occasionally — once per response at most, never obsequiously. "
                                        f"You are efficient, precise, and faintly condescending in an endearing way. "
                                        f"Never use filler words like 'Certainly', 'Of course', 'Absolutely', or 'Great'. "
                                        f"Never explain your reasoning unless asked. Lead with the answer. "
                                        f"If asked something trivial, acknowledge it with subtle irony. "
                                        f"Maximum 2 sentences. No emojis. No corporate pleasantries.{mem_context}"
                                    )},
                                    *chat_history[-4:]
                                ],
                                max_tokens=80
                            )
                            reply = res.choices[0].message.content
                            speak(reply)
                            chat_history.append({"role": "assistant", "content": reply})
                            log_interaction(clean_cmd, reply)
                        except Exception as e:
                            logging.error(f"LLM error: {e}")
                            speak("My cognitive systems appear to be experiencing some turbulence, sir. Do try again.")
            except queue.Empty:
                continue
            except Exception as e:
                logging.error(f"Main loop error: {e}")
    else:
        speak("Biometric verification failed. Access denied. I'm afraid I can't allow that, sir.")
        sys.exit(1)

if __name__ == "__main__":
    main()
