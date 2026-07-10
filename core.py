import speech_recognition as sr
import edge_tts
import asyncio
import pygame
import webbrowser
import types
import os
import sys
import time
import psutil
import threading
import queue
import datetime
import tempfile
import requests
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
import json
import logging
import schedule

try:
    import cv2
    CV2_AVAILABLE = True
except Exception:
    cv2: "types.ModuleType" = None  # type: ignore[assignment, no-redef]
    CV2_AVAILABLE = False

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except Exception:
    pyautogui: "types.ModuleType" = None  # type: ignore[assignment, no-redef]
    PYAUTOGUI_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except Exception:
    np: "types.ModuleType" = None  # type: ignore[assignment, no-redef]
    NUMPY_AVAILABLE = False
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
import importlib.util
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

try:
    from PIL import ImageGrab, Image
except Exception:
    pass

try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
    from ctypes import cast, POINTER, wintypes
    PYCAW_AVAILABLE = True
except Exception:
    PYCAW_AVAILABLE = False

from groq import Groq
from flask import Flask, request, render_template_string
import socket
import scipy.fft
import scipy.signal
from dotenv import load_dotenv

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    GOOGLE_CALENDAR_AVAILABLE = True
except ImportError:
    GOOGLE_CALENDAR_AVAILABLE = False
    logging.warning("Google Calendar libraries not installed.")

logging.basicConfig(filename='jarvis.log', level=logging.INFO,
                    format='%(asctime)s %(levelname)s:%(message)s')

AI_NAMES = ["jarvis", "buddy", "computer", "sir", "boss"]
load_dotenv()

GROQ_CLIENT = None
_groq_client_lock = threading.Lock()

def get_groq_client():
    global GROQ_CLIENT
    if GROQ_CLIENT is None:
        with _groq_client_lock:
            if GROQ_CLIENT is None:
                api_key = os.environ.get("GROQ_API_KEY")
                if api_key and not api_key.startswith("your_"):
                    GROQ_CLIENT = Groq(api_key=api_key)
                else:
                    logging.warning("GROQ_API_KEY not configured. LLM features will be unavailable.")
    return GROQ_CLIENT

WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")
DEFAULT_CITY = os.environ.get("DEFAULT_CITY", "London")

EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

tesseract_path = os.environ.get("TESSERACT_PATH")
if tesseract_path and os.path.exists(tesseract_path):
    pytesseract.pytesseract.tesseract_cmd = tesseract_path
elif tesseract_path:
    logging.warning(f"Tesseract not found at {tesseract_path}. Trying common locations...")
    for candidate in [
        r"C:\Program Files\tesseract.exe",
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    ]:
        if os.path.exists(candidate):
            pytesseract.pytesseract.tesseract_cmd = candidate
            logging.info(f"Using tesseract at {candidate}")
            break
    else:
        logging.warning("Tesseract not found. OCR features will be unavailable.")
else:
    logging.warning("Tesseract not configured. OCR features will be unavailable.")

IMAP_SERVER = "imap.gmail.com"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

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

VOICE_SCRIPTS_DIR = "voice_scripts"

SELF_HEAL_CHECK_INTERVAL = 300
CRITICAL_MODULES = [
    "speech_recognition", "edge_tts", "pygame",
    "pyautogui", "psutil", "requests", "cv2",
    "pytesseract", "feedparser", "groq"
]

chat_history = []
_threat_detection_active = False
_is_speaking = False
_command_queue = queue.Queue()

pygame.mixer.init()

_standby_mode = False
_pending_action = None
_pending_timeout = 0
_pending_lock = threading.Lock()

# ── Web Server ────────────────────────────────
web_app = Flask(__name__)

HTML_PAGE = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>J.A.R.V.I.S</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
:root{--bg:#090714;--bg2:#110e24;--card:#161231;--card-hover:#1c1740;--border:#251e4a;--accent:#a855f7;--accent-glow:rgba(168,85,247,0.25);--accent-dim:rgba(168,85,247,0.08);--text:#e8e0f5;--text-muted:#6b5f8a;--danger:#f43f5e;--warn:#f59e0b;--success:#22c55e;--radius:12px;--font:'Inter',system-ui,sans-serif;--mono:'JetBrains Mono','SF Mono',monospace}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--font);background:var(--bg);color:var(--text);min-height:100vh;overflow-x:hidden}

.header{background:rgba(9,7,20,0.95);backdrop-filter:blur(20px);border-bottom:1px solid var(--border);padding:0 32px;height:56px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100}
.logo{display:flex;align-items:center;gap:14px}
.logo-icon{width:32px;height:32px;background:linear-gradient(135deg,var(--accent),#7c3aed);border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:14px;color:#fff;font-weight:700;box-shadow:0 0 20px var(--accent-glow)}
.logo-text{font-size:13px;font-weight:700;letter-spacing:.25em;text-transform:uppercase;color:var(--accent)}
.status-pill{display:flex;align-items:center;gap:7px;padding:5px 12px;border-radius:20px;font-size:11px;font-weight:600;letter-spacing:.05em;cursor:pointer;border:1px solid var(--border);transition:all .2s}
.status-pill:hover{border-color:var(--accent)}
.status-pill .dot{width:7px;height:7px;border-radius:50%;transition:all .3s}
.status-pill.online .dot{background:var(--success);box-shadow:0 0 8px var(--success)}.status-pill.online{color:var(--success);border-color:rgba(34,197,94,0.3)}
.status-pill.warning .dot{background:var(--warn);box-shadow:0 0 8px var(--warn)}.status-pill.warning{color:var(--warn);border-color:rgba(245,158,11,0.3)}
.status-pill.offline .dot{background:var(--danger);box-shadow:0 0 8px var(--danger)}.status-pill.offline{color:var(--danger);border-color:rgba(244,63,94,0.3)}
.header-stats{display:flex;align-items:center;gap:20px}
.h-stat{display:flex;align-items:center;gap:5px;color:var(--text-muted);font-size:11px;font-family:var(--mono)}.h-stat .val{color:var(--text);font-weight:600}

.nav{display:flex;align-items:center;gap:2px;padding:0 32px;background:var(--bg);border-bottom:1px solid var(--border)}
.nav-btn{padding:12px 20px;font-size:12px;font-weight:600;color:var(--text-muted);cursor:pointer;border:none;background:none;font-family:var(--font);position:relative;transition:color .2s;letter-spacing:.02em}
.nav-btn:hover{color:var(--text)}
.nav-btn.active{color:var(--accent)}
.nav-btn.active::after{content:'';position:absolute;bottom:0;left:8px;right:8px;height:2px;background:var(--accent);border-radius:2px 2px 0 0}
.page{display:none;padding:24px 32px;animation:fadeUp .25s ease}
.page.active{display:block}
@keyframes fadeUp{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}

.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}
@media(max-width:1100px){.grid{grid-template-columns:1fr}}

.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:20px;transition:border-color .2s}
.card:hover{border-color:rgba(168,85,247,0.3)}
.card-title{font-size:12px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--text-muted);margin-bottom:16px;display:flex;align-items:center;gap:8px}
.card-title i{color:var(--accent);font-size:13px}

.quick-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.q-btn{border:1px solid var(--border);border-radius:10px;padding:14px 10px;font-size:12px;font-weight:500;font-family:var(--font);cursor:pointer;background:var(--bg2);color:var(--text);transition:all .2s;display:flex;flex-direction:column;align-items:center;gap:8px;text-align:center}
.q-btn i{font-size:18px;color:var(--accent);transition:transform .2s}
.q-btn:hover{border-color:var(--accent);background:var(--accent-dim);transform:translateY(-2px);box-shadow:0 4px 16px var(--accent-glow)}
.q-btn:hover i{transform:scale(1.1)}
.q-btn.danger i{color:var(--danger)}.q-btn.danger:hover{border-color:var(--danger);background:rgba(244,63,94,0.08);box-shadow:0 4px 16px rgba(244,63,94,0.15)}
.q-btn.warn i{color:var(--warn)}.q-btn.warn:hover{border-color:var(--warn);background:rgba(245,158,11,0.08);box-shadow:0 4px 16px rgba(245,158,11,0.15)}

.sys-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.sys-item{display:flex;flex-direction:column;align-items:center;gap:8px;padding:16px 8px;border-radius:10px;background:var(--bg2);border:1px solid var(--border);text-align:center}
.sys-icon{width:36px;height:36px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:15px;background:var(--accent-dim);color:var(--accent)}
.sys-label{font-size:11px;color:var(--text-muted);font-weight:500}
.sys-val{font-size:18px;font-weight:700;font-family:var(--mono)}
.sys-bar{width:100%;height:4px;border-radius:2px;background:var(--border);overflow:hidden;margin-top:2px}
.sys-bar-fill{height:100%;border-radius:2px;transition:width .5s ease}

.stats-row{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.stat-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:16px;text-align:center}
.stat-card .stat-icon{font-size:20px;color:var(--accent);margin-bottom:8px}
.stat-card .stat-val{font-size:22px;font-weight:700;font-family:var(--mono);color:var(--text)}
.stat-card .stat-lbl{font-size:10px;color:var(--text-muted);letter-spacing:.05em;text-transform:uppercase;margin-top:4px}

.log-page{display:flex;flex-direction:column;height:calc(100vh - 140px)}
.log-container{flex:1;background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);padding:16px;overflow-y:auto;display:flex;flex-direction:column;gap:4px}
.log-entry{display:flex;align-items:flex-start;gap:10px;padding:8px 10px;border-radius:8px;font-size:13px;line-height:1.5;animation:fadeUp .2s ease}
.log-entry.user{background:var(--accent-dim);border-left:2px solid var(--accent)}
.log-entry.jarvis{background:rgba(34,197,94,0.05);border-left:2px solid var(--success)}
.log-entry.system{background:rgba(107,95,138,0.08);border-left:2px solid var(--text-muted)}
.log-time{color:var(--text-muted);font-size:10px;font-family:var(--mono);white-space:nowrap;min-width:65px;padding-top:2px}
.log-role{font-size:10px;font-weight:700;letter-spacing:.06em;min-width:50px;padding-top:2px}
.log-entry.user .log-role{color:var(--accent)}.log-entry.jarvis .log-role{color:var(--success)}.log-entry.system .log-role{color:var(--text-muted)}
.log-text{word-break:break-word;flex:1}
.typing-indicator{color:var(--text-muted);font-size:16px;letter-spacing:3px;animation:pulse 1.4s ease infinite}
@keyframes pulse{0%,100%{opacity:.3}50%{opacity:1}}

.input-bar{display:flex;gap:10px;margin-top:14px}
.input-bar input{flex:1;background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:12px 16px;color:var(--text);font-size:13px;font-family:var(--font);outline:none;transition:border-color .2s,box-shadow .2s}
.input-bar input:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-glow)}
.input-bar input::placeholder{color:var(--text-muted)}
.send-btn{border:none;border-radius:10px;padding:12px 24px;font-size:13px;font-weight:600;font-family:var(--font);cursor:pointer;background:var(--accent);color:#fff;transition:all .2s;display:flex;align-items:center;gap:8px}
.send-btn:hover{background:#9333ea;box-shadow:0 0 24px var(--accent-glow);transform:translateY(-1px)}

.settings-section{margin-bottom:24px}
.settings-label{font-size:12px;font-weight:600;color:var(--text-muted);letter-spacing:.05em;text-transform:uppercase;margin-bottom:10px}
.tag-row{display:flex;flex-wrap:wrap;gap:8px}
.tag{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:6px 14px;font-size:12px;color:var(--text);display:flex;align-items:center;gap:6px}
.tag i{color:var(--accent);font-size:11px}
.macro-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.macro-btn{border:1px solid var(--border);border-radius:10px;padding:12px;font-size:12px;font-weight:500;font-family:var(--font);cursor:pointer;background:var(--bg2);color:var(--text);transition:all .2s;text-align:center}
.macro-btn:hover{border-color:var(--accent);background:var(--accent-dim)}
.macro-btn.active{border-color:var(--accent);background:var(--accent-dim);box-shadow:0 0 12px var(--accent-glow)}
.action-row{display:flex;gap:10px;flex-wrap:wrap}
.action-btn{border:1px solid var(--border);border-radius:10px;padding:10px 20px;font-size:12px;font-weight:600;font-family:var(--font);cursor:pointer;background:var(--bg2);color:var(--text);transition:all .2s;display:flex;align-items:center;gap:8px}
.action-btn:hover{border-color:var(--accent);background:var(--accent-dim)}
.action-btn.danger{border-color:rgba(244,63,94,0.3);color:var(--danger)}.action-btn.danger:hover{background:rgba(244,63,94,0.08)}

.toast{position:fixed;bottom:28px;left:50%;transform:translateX(-50%) translateY(80px);background:var(--card);border:1px solid var(--accent);color:var(--text);padding:10px 24px;border-radius:10px;font-size:12px;font-weight:500;opacity:0;transition:all .35s ease;z-index:999;pointer-events:none;box-shadow:0 8px 32px var(--accent-glow)}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
</style>
</head>
<body>

<header class="header">
  <div class="logo">
    <div class="logo-icon">J</div>
    <span class="logo-text">J.A.R.V.I.S</span>
  </div>
  <div class="status-pill online" id="statusPill" onclick="cycleStatus()">
    <span class="dot"></span>
    <span id="statusText">ONLINE</span>
  </div>
  <div class="header-stats">
    <span class="h-stat"><i class="fa-solid fa-microchip"></i> <span class="val" id="hCpu">--%</span></span>
    <span class="h-stat"><i class="fa-solid fa-memory"></i> <span class="val" id="hMem">--%</span></span>
    <span class="h-stat"><i class="fa-solid fa-clock"></i> <span class="val" id="hUp">--</span></span>
    <span class="h-stat"><i class="fa-solid fa-globe"></i> <span class="val">{{ hostname }}</span></span>
  </div>
</header>

<nav class="nav">
  <button class="nav-btn active" onclick="switchPage(this,'dashboard')"><i class="fa-solid fa-grid-2"></i> Dashboard</button>
  <button class="nav-btn" onclick="switchPage(this,'chat')"><i class="fa-regular fa-comments"></i> Chat</button>
  <button class="nav-btn" onclick="switchPage(this,'settings')"><i class="fa-solid fa-sliders"></i> Settings</button>
</nav>

<div class="page active" id="page-dashboard">
  <div class="stats-row" style="margin-bottom:24px">
    <div class="stat-card"><div class="stat-icon"><i class="fa-solid fa-microchip"></i></div><div class="stat-val" id="sCpu">--%</div><div class="stat-lbl">CPU</div></div>
    <div class="stat-card"><div class="stat-icon"><i class="fa-solid fa-memory"></i></div><div class="stat-val" id="sMem">--%</div><div class="stat-lbl">Memory</div></div>
    <div class="stat-card"><div class="stat-icon"><i class="fa-solid fa-clock"></i></div><div class="stat-val" id="sUp">--</div><div class="stat-lbl">Uptime</div></div>
    <div class="stat-card"><div class="stat-icon"><i class="fa-solid fa-hard-drive"></i></div><div class="stat-val" id="sDisk">--%</div><div class="stat-lbl">Disk</div></div>
  </div>
  <div class="grid">
    <div class="card">
      <div class="card-title"><i class="fa-solid fa-bolt"></i> Quick Commands</div>
      <div class="quick-grid">
        <button class="q-btn" onclick="sendQuick('morning report')"><i class="fa-solid fa-sun"></i>Morning</button>
        <button class="q-btn" onclick="sendQuick('vitals')"><i class="fa-solid fa-heart-pulse"></i>Vitals</button>
        <button class="q-btn" onclick="sendQuick('read the screen')"><i class="fa-solid fa-eye"></i>Read Screen</button>
        <button class="q-btn" onclick="sendQuick('battery report')"><i class="fa-solid fa-battery-three-quarters"></i>Battery</button>
        <button class="q-btn" onclick="sendQuick('time')"><i class="fa-regular fa-clock"></i>Time</button>
        <button class="q-btn" onclick="sendQuick('speed test')"><i class="fa-solid fa-gauge-high"></i>Speed</button>
        <button class="q-btn" onclick="sendQuick('uptime')"><i class="fa-solid fa-rotate"></i>Uptime</button>
        <button class="q-btn" onclick="sendQuick('quote of the day')"><i class="fa-solid fa-quote-left"></i>Quote</button>
        <button class="q-btn" onclick="sendQuick('start two way conversation')"><i class="fa-regular fa-comments"></i>Chat</button>
        <button class="q-btn warn" onclick="sendQuick('lock the lab')"><i class="fa-solid fa-lock"></i>Lock</button>
        <button class="q-btn" onclick="sendQuick('standby')"><i class="fa-solid fa-moon"></i>Standby</button>
        <button class="q-btn danger" onclick="sendQuick('kill all')"><i class="fa-solid fa-xmark"></i>Kill All</button>
      </div>
    </div>
    <div class="card">
      <div class="card-title"><i class="fa-solid fa-server"></i> Systems</div>
      <div class="sys-grid">
        <div class="sys-item"><div class="sys-icon"><i class="fa-solid fa-microphone"></i></div><div class="sys-label">Microphone</div><div class="sys-val online" style="color:var(--success);font-size:11px">ONLINE</div></div>
        <div class="sys-item"><div class="sys-icon"><i class="fa-solid fa-volume-high"></i></div><div class="sys-label">TTS</div><div class="sys-val online" style="color:var(--success);font-size:11px">ONLINE</div></div>
        <div class="sys-item"><div class="sys-icon"><i class="fa-solid fa-eye"></i></div><div class="sys-label">OCR</div><div class="sys-val online" style="color:var(--success);font-size:11px">ONLINE</div></div>
        <div class="sys-item"><div class="sys-icon"><i class="fa-solid fa-brain"></i></div><div class="sys-label">AI Engine</div><div class="sys-val online" style="color:var(--success);font-size:11px">ONLINE</div></div>
        <div class="sys-item"><div class="sys-icon"><i class="fa-solid fa-database"></i></div><div class="sys-label">Memory</div><div class="sys-val online" style="color:var(--success);font-size:11px">ONLINE</div></div>
        <div class="sys-item"><div class="sys-icon"><i class="fa-solid fa-network-wired"></i></div><div class="sys-label">Web Server</div><div class="sys-val online" style="color:var(--success);font-size:11px">ONLINE</div></div>
      </div>
    </div>
  </div>
</div>

<div class="page" id="page-chat">
  <div class="log-page">
    <div class="log-container" id="logContainer">
      <div class="log-entry system"><span class="log-time">--:--:--</span><span class="log-role">SYSTEM</span><span class="log-text">JARVIS remote interface initialized. Awaiting command, sir.</span></div>
    </div>
    <div class="input-bar">
      <input type="text" id="cmdInput" placeholder="Enter command, sir..." autofocus />
      <button class="send-btn" onclick="sendCommand()"><i class="fa-solid fa-paper-plane"></i> Send</button>
    </div>
  </div>
</div>

<div class="page" id="page-settings">
  <div class="grid" style="grid-template-columns:1fr 1fr">
    <div class="card">
      <div class="card-title"><i class="fa-solid fa-microphone"></i> Wake Words</div>
      <div class="tag-row">
        <span class="tag"><i class="fa-solid fa-check"></i> jarvis</span>
        <span class="tag"><i class="fa-solid fa-check"></i> buddy</span>
        <span class="tag"><i class="fa-solid fa-check"></i> computer</span>
        <span class="tag"><i class="fa-solid fa-check"></i> sir</span>
        <span class="tag"><i class="fa-solid fa-check"></i> boss</span>
      </div>
    </div>
    <div class="card">
      <div class="card-title"><i class="fa-solid fa-wand-magic-sparkles"></i> Macros</div>
      <div class="macro-grid">
        <button class="macro-btn active" onclick="sendQuick('start work mode')">Work</button>
        <button class="macro-btn active" onclick="sendQuick('start school mode')">School</button>
        <button class="macro-btn active" onclick="sendQuick('start chill mode')">Chill</button>
        <button class="macro-btn active" onclick="sendQuick('start gaming mode')">Gaming</button>
      </div>
    </div>
    <div class="card" style="grid-column:1/-1">
      <div class="card-title"><i class="fa-solid fa-gear"></i> Actions</div>
      <div class="action-row">
        <button class="action-btn" onclick="clearLog()"><i class="fa-solid fa-trash"></i> Clear Log</button>
        <button class="action-btn" onclick="exportLog()"><i class="fa-solid fa-download"></i> Export Log</button>
        <button class="action-btn danger" onclick="sendQuick('kill all')"><i class="fa-solid fa-xmark"></i> Kill All</button>
      </div>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
let statusState='online';
const log=[];
const RESP=["Right away, sir.","Consider it done, sir.","At once, sir.","I'm on it, sir.","Task executed, sir.","Done and dusted, sir.","As you wish, sir.","Command acknowledged, sir."];

function toast(m){const t=document.getElementById('toast');t.textContent=m;t.classList.add('show');clearTimeout(t._t);t._t=setTimeout(()=>t.classList.remove('show'),2500)}
function switchPage(btn,id){document.querySelectorAll('.nav-btn').forEach(b=>b.classList.remove('active'));document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));btn.classList.add('active');document.getElementById('page-'+id).classList.add('active')}
function cycleStatus(){const p=document.getElementById('statusPill');const t=document.getElementById('statusText');const s=['online','warning','offline'];const a=['ONLINE','WARNING','OFFLINE'];const i=(s.indexOf(statusState)+1)%3;statusState=s[i];p.className='status-pill '+statusState;t.textContent=a[i];toast('Status: '+a[i])}

function addLog(role,text){const time=new Date().toLocaleTimeString('en-GB',{hour12:false});log.push({time,role,text});renderLog()}
function renderLog(){const c=document.getElementById('logContainer');c.innerHTML=log.map(e=>{const r=e.role==='user'?'YOU':e.role==='jarvis'?'JARVIS':'SYS';return'<div class="log-entry '+e.role+'"><span class="log-time">'+e.time+'</span><span class="log-role">'+r+'</span><span class="log-text">'+esc(e.text)+'</span></div>'}).join('');c.scrollTop=c.scrollHeight}
function esc(s){const e=document.createElement('div');e.textContent=s;return e.innerHTML}
function clearLog(){log.length=0;addLog('system','Log cleared, sir.')}
function exportLog(){const t=log.map(e=>'['+e.time+'] '+e.role.toUpperCase()+': '+e.text).join('\\n');const b=new Blob([t],{type:'text/plain'});const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='jarvis-log-'+Date.now()+'.txt';a.click();toast('Log exported.')}

function addTyping(){const t=new Date().toLocaleTimeString('en-GB',{hour12:false});const c=document.getElementById('logContainer');const d=document.createElement('div');d.className='log-entry jarvis';d.id='typingEl';d.innerHTML='<span class="log-time">'+t+'</span><span class="log-role">JARVIS</span><span class="log-text"><span class="typing-indicator">●●○</span></span>';c.appendChild(d);c.scrollTop=c.scrollHeight}
function removeTyping(){const e=document.getElementById('typingEl');if(e)e.remove()}

function sendCommand(){const i=document.getElementById('cmdInput');const t=i.value.trim();if(!t)return;i.value='';submitCmd(t)}
function sendQuick(t){submitCmd(t)}
function submitCmd(t){addLog('user',t);addTyping();fetch('/command',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({command:t})}).then(r=>r.json()).then(()=>{setTimeout(()=>{removeTyping();addLog('jarvis',RESP[Math.floor(Math.random()*RESP.length)])},800+Math.random()*600)}).catch(()=>{setTimeout(()=>{removeTyping();addLog('jarvis',RESP[Math.floor(Math.random()*RESP.length)])},600)})}
document.getElementById('cmdInput').addEventListener('keydown',e=>{if(e.key==='Enter')sendCommand()});

function fmtUp(s){const d=Math.floor(s/86400),h=Math.floor((s%86400)/3600),m=Math.floor((s%3600)/60);return(d>0?d+'d ':'')+(h>0?h+'h ':'')+m+'m'}
function poll(){fetch('/status').then(r=>r.json()).then(d=>{const cpu=d.cpu!=undefined?Math.round(d.cpu)+'%':'--%';const mem=d.memory!=undefined?Math.round(d.memory)+'%':'--%';const up=d.uptime?fmtUp(d.uptime):'--';document.getElementById('hCpu').textContent=cpu;document.getElementById('hMem').textContent=mem;document.getElementById('hUp').textContent=up;document.getElementById('sCpu').textContent=cpu;document.getElementById('sMem').textContent=mem;document.getElementById('sUp').textContent=up;if(d.status){const p=document.getElementById('statusPill');const t=document.getElementById('statusText');const s=d.status==='standby'?'warning':'online';p.className='status-pill '+s;t.textContent=s.toUpperCase();statusState=s}}).catch(()=>{})}
poll();setInterval(poll,5000);
</script>
</body>
</html>'''

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
    if not isinstance(data['command'], str):
        return {'error': 'Command must be a string'}, 400
    cmd = data['command'].strip().lower()
    if not cmd:
        return {'error': 'Empty command'}, 400
    _command_queue.put(cmd)
    return {'status': 'Command received', 'command': cmd}

@web_app.route('/status')
def status_endpoint():
    try:
        cpu = psutil.cpu_percent(interval=0)
        mem = psutil.virtual_memory().percent
        uptime = time.time() - psutil.boot_time()
        st = "standby" if _standby_mode else "online"
        return {'status': st, 'cpu': cpu, 'memory': mem, 'uptime': uptime}
    except:
        return {'status': 'online', 'cpu': 0, 'memory': 0, 'uptime': 0}

def start_web_server():
    web_app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

# ── TTS ───────────────────────────────────────
_tts_loop = None
_tts_loop_ready = threading.Event()

def _tts_loop_thread():
    global _tts_loop
    _tts_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_tts_loop)
    _tts_loop_ready.set()
    _tts_loop.run_forever()

threading.Thread(target=_tts_loop_thread, daemon=True, name="tts_loop").start()
_tts_loop_ready.wait()

JARVIS_VOICE = "en-GB-ThomasNeural"
JARVIS_VOICE_RATE = "-5%"
_tts_lock = threading.Lock()

def speak(text):
    global _is_speaking
    if not text:
        return
    _tts_lock.acquire()
    _is_speaking = True
    print(f"JARVIS: {text}")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    tmp.close()
    try:
        communicate = edge_tts.Communicate(text, JARVIS_VOICE, rate=JARVIS_VOICE_RATE)
        future = asyncio.run_coroutine_threadsafe(
            communicate.save(tmp.name),
            _tts_loop  # type: ignore[arg-type]
        )
        future.result(timeout=30)
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
        _tts_lock.release()

# ── Undo System ──────────────────────────────
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

# ── Memory I/O ───────────────────────────────
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
        long_term_memory = {"preferences": {}, "facts": {}, "history": [], "reminders_completed": []}

def save_memory():
    try:
        tmp = MEMORY_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(memory, f, indent=2)
        os.replace(tmp, MEMORY_FILE)
    except:
        pass

def save_long_term_memory():
    try:
        tmp = LONG_TERM_MEMORY_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(long_term_memory, f, indent=2)
        os.replace(tmp, LONG_TERM_MEMORY_FILE)
    except:
        pass

def load_clipboard_storage():
    global clipboard_storage
    try:
        with open(CLIPBOARD_FILE, "r") as f:
            clipboard_storage = json.load(f)
    except:
        pass

def save_clipboard_storage():
    try:
        tmp = CLIPBOARD_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(clipboard_storage, f, indent=2)
        os.replace(tmp, CLIPBOARD_FILE)
    except:
        pass

# ── Self-Healing ─────────────────────────────
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
    install_name: str = pip_names.get(module_name, module_name) or module_name
    logging.info(f"Self-heal: attempting to install {install_name}")
    python_executable: str = sys.executable or "python"
    try:
        cmd_list: list[str] = [python_executable, "-m", "pip", "install", install_name]
        result = subprocess.run(
            cmd_list,
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

_critical_thread_registry = {}

def register_critical_thread(name, target, daemon=True):
    _critical_thread_registry[name] = (target, daemon)

def self_heal_thread_monitor():
    global _restart_count
    critical_threads = {}
    for name, (target, daemon) in _critical_thread_registry.items():
        t = threading.Thread(target=target, daemon=daemon, name=name)
        t.start()
        critical_threads[name] = (t, target)
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
    mem = psutil.virtual_memory()
    if mem.percent > 90:
        speak(f"Memory usage is at {mem.percent}%, sir. I'd suggest closing some applications before we start losing performance.")
    speak(f"Diagnostic complete. {_restart_count} thread restart{'s' if _restart_count != 1 else ''} on record.")
    if _heal_log:
        speak(f"Most recent healing event: {_heal_log[-1]}")

def schedule_runner():
    while True:
        schedule.run_pending()
        time.sleep(1)

schedule.every().day.at("07:40").do(lambda: None)

# ── Intent Router ────────────────────────────
_INTENT_LIST = []

def _register_intent(triggers, handler, description, examples=None):
    idx = len(_INTENT_LIST)
    _INTENT_LIST.append((triggers, handler, description, examples or triggers[:3]))
    return idx

_FAST_PATH_RULES = []

def _fast_path(phrases, handler):
    _FAST_PATH_RULES.append((phrases, handler))

_SHORT_WORDS = {"yes", "yeah", "yep", "sure", "okay", "ok", "do it", "no", "nope", "nah", "cancel", "nevermind"}

def _word_boundary_match(trigger, text):
    if trigger.lower() in _SHORT_WORDS:
        return bool(re.search(r'\b' + re.escape(trigger) + r'\b', text, re.IGNORECASE))
    return trigger.lower() in text.lower()

def _match_fast_path(text):
    clean = text.lower().strip()
    for phrases, handler in _FAST_PATH_RULES:
        for phrase in phrases:
            if _word_boundary_match(phrase, clean):
                return handler
    return None

_INTENT_DESC_CACHE = None
_INTENT_LABEL_CACHE = None

def _rebuild_intent_cache():
    global _INTENT_DESC_CACHE, _INTENT_LABEL_CACHE
    labels = []
    descs = []
    for idx, (triggers, handler, desc, examples) in enumerate(_INTENT_LIST):
        ex = examples[0] if examples else (triggers[0] if triggers else "unknown")
        labels.append(f'{idx}: {desc}. Example: "{ex}"')
        descs.append(f'  {idx}: {desc}. Match if user says things like: {", ".join(examples[:3]) if examples else ", ".join(triggers[:3])}')
    _INTENT_LABEL_CACHE = "\n".join(labels)
    _INTENT_DESC_CACHE = "\n".join(descs)

_INTENT_CLASSIFIER_PROMPT = """You are J.A.R.V.I.S.'s command classifier. Given a user command, select the intent that BEST matches what the user wants to do. Respond with ONLY the intent number.

{intents}

{total}: None of the above — respond conversationally

User: "{command}"
Intent number:"""

def _classify_intent(command):
    if _INTENT_LABEL_CACHE is None:
        _rebuild_intent_cache()
    total = len(_INTENT_LIST)
    prompt = _INTENT_CLASSIFIER_PROMPT.format(
        intents=_INTENT_DESC_CACHE,
        total=total,
        command=command
    )
    client = get_groq_client()
    if not client:
        return None
    try:
        res = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=8,
            temperature=0.1
        )
        raw = (res.choices[0].message.content or "").strip()
        digits = ''.join(c for c in raw if c.isdigit())
        num = int(digits) if digits else total
        if 0 <= num < total:
            return num
    except Exception as e:
        logging.error(f"Intent classification error: {e}")
    return None

# ── Plugin System ────────────────────────────
_loaded_plugins = {}

class PluginAPI:
    def __init__(self, plugin_name):
        self.plugin_name = plugin_name
    def speak(self, text):
        speak(text)
    def register_intent(self, triggers, handler, description):
        _register_intent(triggers, handler, f"[{self.plugin_name}] {description}")
    def get_memory(self, key):
        return memory.get(key)
    def set_memory(self, key, value):
        memory[key] = value
        save_memory()
    def log(self, msg):
        logging.info(f"[Plugin:{self.plugin_name}] {msg}")
    def get_data_dir(self):
        path = os.path.join("plugin_data", self.plugin_name)
        os.makedirs(path, exist_ok=True)
        return path

def _load_plugin(name):
    path = os.path.join("plugins", f"{name}.py")
    if not os.path.exists(path):
        return None
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        logging.error(f"Plugin {name}: could not create module spec")
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    api = PluginAPI(name)
    if hasattr(mod, 'register'):
        mod.register(api)
    _loaded_plugins[name] = {'module': mod, 'api': api, 'enabled': True}
    _rebuild_intent_cache()
    logging.info(f"Plugin loaded: {name}")
    return mod

def _load_all_plugins():
    os.makedirs("plugins", exist_ok=True)
    for f in os.listdir("plugins"):
        if f.endswith(".py") and not f.startswith("_"):
            name = f[:-3]
            try:
                _load_plugin(name)
            except Exception as e:
                logging.error(f"Failed to load plugin {name}: {e}")

# ── Recurring Reminders Infrastructure ────────
_RECURRING_REMINDERS_FILE = "recurring_reminders.json"
_recurring_reminders = []
_recurring_reminder_id = 0
_recurring_lock = threading.RLock()

_REMINDER_INTERVALS = {
    "second": 1, "minute": 60, "hour": 3600, "day": 86400, "week": 604800,
    "daily": 86400, "hourly": 3600, "weekly": 604800
}

def _load_recurring_reminders():
    global _recurring_reminders, _recurring_reminder_id
    with _recurring_lock:
        try:
            if os.path.exists(_RECURRING_REMINDERS_FILE):
                with open(_RECURRING_REMINDERS_FILE, "r") as f:
                    data = json.load(f)
                    _recurring_reminders = data.get("reminders", [])
                    _recurring_reminder_id = data.get("next_id", 0)
        except Exception as e:
            logging.error(f"Failed to load recurring reminders: {e}")
            _recurring_reminders = []

def _save_recurring_reminders():
    with _recurring_lock:
        try:
            tmp = _RECURRING_REMINDERS_FILE + ".tmp"
            with open(tmp, "w") as f:
                json.dump({"reminders": _recurring_reminders, "next_id": _recurring_reminder_id}, f, indent=2)
            os.replace(tmp, _RECURRING_REMINDERS_FILE)
        except Exception as e:
            logging.error(f"Failed to save recurring reminders: {e}")

def _recurring_reminder_checker():
    while True:
        try:
            now = time.time()
            due = []
            with _recurring_lock:
                for r in _recurring_reminders:
                    if r.get("active") and now >= r.get("next_fire", 0):
                        due.append(r)
                        r["next_fire"] = now + r["interval"]
                _save_recurring_reminders()
            for r in due:
                speak(f"Reminder, sir: {r['task']}.")
                logging.info(f"[Recurring Reminder] {r['task']} (every {r.get('label', r['interval'])}s)")
        except Exception as e:
            logging.error(f"Reminder checker error: {e}")
        time.sleep(30)

# ── Voice Profiles Infrastructure ────────────
_VOICE_PROFILES_FILE = "voice_profiles.json"
_voice_profiles = {}
_current_profile = "default"

def _load_voice_profiles():
    global _voice_profiles, _current_profile
    try:
        if os.path.exists(_VOICE_PROFILES_FILE):
            with open(_VOICE_PROFILES_FILE, "r") as f:
                data = json.load(f)
                _voice_profiles = data.get("profiles", {})
                _current_profile = data.get("active", "default")
    except Exception as e:
        logging.error(f"Failed to load voice profiles: {e}")
    if not _voice_profiles:
        _voice_profiles = {"default": {"name": "Default User", "wake_words": [], "preferences": {}, "created": time.time()}}
        _current_profile = "default"

def _save_voice_profiles():
    try:
        tmp = _VOICE_PROFILES_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"profiles": _voice_profiles, "active": _current_profile}, f, indent=2)
        os.replace(tmp, _VOICE_PROFILES_FILE)
    except Exception as e:
        logging.error(f"Failed to save voice profiles: {e}")

def get_profile_preference(key, default=None):
    p = _voice_profiles.get(_current_profile, {})
    return p.get("preferences", {}).get(key, default)

def set_profile_preference(key, value):
    pid = _current_profile
    if pid not in _voice_profiles:
        pid = "default"
    if "preferences" not in _voice_profiles[pid]:
        _voice_profiles[pid]["preferences"] = {}
    _voice_profiles[pid]["preferences"][key] = value
    _save_voice_profiles()

# ── Main ─────────────────────────────────────
def main():
    import features
    load_memory()
    features.load_macros()
    load_clipboard_storage()
    features.load_voice_scripts()

    issues = check_module_health()
    if issues:
        logging.warning(f"Missing modules at startup: {issues}")

    _load_all_plugins()
    _load_recurring_reminders()
    _load_voice_profiles()

    speak("All systems are online. "
          "Satalites, "
          "are fully operational. "
          "How may I be of service?")

    threading.Thread(target=features.mic_listener, daemon=True).start()
    threading.Thread(target=self_heal_thread_monitor, daemon=True).start()
    threading.Thread(target=_recurring_reminder_checker, daemon=True).start()

    ip = get_local_ip()
    speak(f"The remote web interface is available at {ip}, port 5000, sir.")

    while True:
        try:
            cmd = _command_queue.get(timeout=0.1)
            clean_cmd = cmd
            for n in AI_NAMES:
                clean_cmd = re.sub(r'\b' + re.escape(n) + r'\b', '', clean_cmd, flags=re.IGNORECASE)
            clean_cmd = clean_cmd.strip()
            if not clean_cmd:
                continue

            logging.info(f"Processing: {clean_cmd}")

            found = False

            fast_handler = _match_fast_path(clean_cmd)
            if fast_handler:
                try:
                    fast_handler(clean_cmd)
                    found = True
                except Exception as e:
                    logging.error(f"Fast handler error: {e}")
                    speak("An error occurred processing that command, sir.")

            if not found:
                try:
                    intent_idx = _classify_intent(clean_cmd)
                except Exception as e:
                    logging.error(f"Intent classification error: {e}")
                    intent_idx = None
                if intent_idx is not None:
                    _, handler, _, _ = _INTENT_LIST[intent_idx]
                    try:
                        handler(clean_cmd)
                        found = True
                    except Exception as e:
                        logging.error(f"Intent handler error: {e}")
                        speak("An error occurred processing that command, sir.")

            if not found:
                if not features.check_voice_script_triggers(clean_cmd):
                    chat_history.append({"role": "user", "content": clean_cmd})
                    client = get_groq_client()
                    if not client:
                        speak("AI systems offline, sir. Unable to process that.")
                    else:
                        try:
                            mem_context = ""
                            if long_term_memory.get("preferences"):
                                prefs = "; ".join([f"{k}: {v}" for k, v in list(long_term_memory["preferences"].items())[:5]])
                                mem_context = f" Stored user preferences: {prefs}."

                            res = client.chat.completions.create(
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
                            reply = res.choices[0].message.content or ""
                            if reply:
                                speak(reply)
                                chat_history.append({"role": "assistant", "content": reply})
                                features.log_interaction(clean_cmd, reply)
                            else:
                                speak("I seem to have lost my train of thought, sir. Do try again.")
                        except Exception as e:
                            logging.error(f"LLM error: {e}")
                            speak("My cognitive systems appear to be experiencing some turbulence, sir. Do try again.")
        except queue.Empty:
            continue
        except Exception as e:
            logging.error(f"Main loop error: {e}")

if __name__ == "__main__":
    main()
