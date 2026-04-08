# Jarvis-Master

J.A.R.V.I.S. – Personal Voice Assistant

J.A.R.V.I.S. (Just A Rather Very Intelligent System) is a fully voice‑controlled, desktop automation assistant inspired by Tony Stark's AI. It combines speech recognition, large language models (LLaMA via Groq), real‑time screen OCR, self‑healing diagnostics, custom voice scripts, and persistent memory into a single Python application.

⚠️ Disclaimer: This project is a personal automation tool. Use at your own risk. It can control your mouse, keyboard, and system settings. Always review the code before running.

⚠️ Make sure to make an authorized_users folder, and in that folder take a picture of yourself, rename it tony.jpg, and put it in there for the face recognition to work.

✨ Features

- 🎙️ Voice Wake Word – Responds to "Jarvis", "Buddy", "Computer", "Sir", or "Boss".
- 🧠 AI‑Powered Conversation – Uses Groq's LLaMA 3.3 for natural, dry‑witted responses.
- 🖥️ Real‑Time Screen OCR – Reads text from any region of your display, finds and clicks on words, and monitors for errors.
- 📜 Custom Voice Scripts – Tell J.A.R.V.I.S. "create a script called CPU alert that warns me when CPU exceeds 80%" and it writes and executes the Python code.
- 🔄 Two‑Way Conversation Mode – Continuous dialogue without repeating the wake word.
- 🛠️ Self‑Healing System – Monitors critical Python modules and restarts crashed threads automatically.
- 💾 Persistent Memory – Remembers preferences, facts, and clipboard snippets across restarts.
- 📅 Google Calendar Integration – Check your next meeting (requires own credentials).
- 📧 Email & Discord – Read latest emails, send messages, post to Discord webhooks.
- 🖱️ System Automation – Open apps, snap windows, control volume, lock workstation, run macros, and more.
- 📡 Web Dashboard – A sleek, remote control interface accessible from any browser on your local network.

📋 Command Examples

| Voice Command | Action |
|---------------|--------|
| "Morning report" | Reads weather and top news headline. |
| "Open Brave" | Launches Brave browser. |
| "Vitals" | Reports CPU, memory, and GPU usage. |
| "Read the screen" | Summarises the current display content. |
| "Start two way conversation" | Begins continuous chat mode. |
| "Create script called backup that copies my Documents folder to an external drive" | Writes a custom automation script. |
| "Kill all" | Closes all browsers and common applications. |
| "Snap left" | Docks the active window to the left half of the screen. |
| "No scrap that" | Undoes the last action. |

> See the Full Command Reference section below for a complete list.

⚙️ Prerequisites

- Python 3.10+ – Download from python.org
- Windows OS – Some features (e.g., pygetwindow, winshell, ctypes power plans) are Windows‑specific.
- Tesseract OCR – Required for screen reading.
  - Download from GitHub UB‑Mannheim/tesseract
  - Install to C:\Program Files\Tesseract-OCR\tesseract.exe (or set custom path in .env).
- A working microphone – For voice commands.

🔧 Installation

1. Clone the repository
   git clone https://github.com/yourusername/jarvis-assistant.git
   cd jarvis-assistant

2. Create a virtual environment (recommended)
   python -m venv venv
   venv\Scripts\activate      (On Windows)
   source venv/bin/activate   (On macOS/Linux)

3. Install dependencies
   pip install -r requirements.txt

4. Set up environment variables
   - Copy the example file:
     copy .env.example .env
   - Open .env in a text editor and fill in your API keys and credentials (see below).

5. Run J.A.R.V.I.S.
   python jarvis.py

On first run, J.A.R.V.I.S. will attempt facial verification (optional). If it fails, it will still start but note the verification warning. You can disable face verification by commenting out the relevant block in main().

🔐 Configuration (.env file)

Create a .env file in the project root with the following variables:

# Required for AI responses
GROQ_API_KEY=gsk_your_groq_api_key_here

# Required for weather reports
WEATHER_API_KEY=your_openweathermap_api_key
DEFAULT_CITY=London

# Required for email features (use a Gmail App Password)
EMAIL_ADDRESS=your_email@gmail.com
EMAIL_PASSWORD=your_app_password

# Optional – for Discord notifications
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Optional – custom Tesseract path if not in default location
TESSERACT_PATH=C:\Program Files\Tesseract-OCR\tesseract.exe

Where to get the keys:
- Groq API Key – console.groq.com/keys (free tier available)
- OpenWeatherMap API Key – openweathermap.org/api (free tier)
- Gmail App Password – Enable 2FA on your Google account, then generate an App Password at myaccount.google.com/apppasswords.
- Discord Webhook URL – In your Discord server, go to Server Settings → Integrations → Webhooks.

⚠️ Never commit your .env file. It is already included in .gitignore.

📁 Project Structure

jarvis-assistant/
├── jarvis.py                 # Main application
├── requirements.txt          # Python dependencies
├── .env.example              # Template for environment variables
├── .gitignore                # Prevents sensitive files from being committed
├── README.md                 # You are here
├── voice_scripts/            # Custom scripts created by voice
├── security_logs/            # Motion detection snapshots (ignored)
├── jarvis_memory.json        # Persistent memory (ignored)
├── macros.json               # User macros (ignored)
└── authorized_users/         # Face recognition images (ignored)

🧪 Troubleshooting

| Problem | Likely Solution |
|---------|-----------------|
| ModuleNotFoundError | Run pip install -r requirements.txt again. Some packages (like pycaw) may require Visual C++ Build Tools. |
| 'NoneType' object has no attribute 'close' | Another application is using the microphone. Close Discord, Zoom, etc., and ensure only one instance of J.A.R.V.I.S. is running. |
| Tesseract not found | Set TESSERACT_PATH in .env to the full path of tesseract.exe. |
| Facial verification fails | Place a clear photo of your face named authorized_user.jpg inside authorized_users/ or comment out the verification block. |
| Voice commands not recognised | Adjust microphone sensitivity by changing rec.adjust_for_ambient_noise(src, duration=0.4) to a longer duration. |

📜 Full Command Reference

Click to expand full list of voice triggers:

Morning Report
Open Brave
Open App
Close Window
Close App
Close Titled Window
Kill All
Vitals
System Health
Read Screen
Threat Detection
Stop Monitoring
Delete Threat Logs
Clear Jarvis Logs
Sleep System
Self Repair
Combat Mode
Cruise Control
Volume Up
Volume Down
Volume Mute
Louder
Quieter
Time
Thank You
Undo
Yes
No
Two-Way Conversation
End Conversation
Self Diagnostic
Heal Report
Create Script
Run Script
List Scripts
Delete Script
Start Screen Monitor
Stop Screen Monitor
Read Region
Click Text
Screen Rule
Remember
Remember Preference
Remember Fact
Recall
Remind Me
Run Macro
List Macros
Create Macro
Delete Macro
Work Mode
School Mode
Chill Mode
Gaming Mode
Save Clipboard
Paste Clipboard
Battery Report
Battery Saver
Split Screen
Snap Left
Snap Right
Full Screen
Lock Lab
Log Off
Confirm Logout
Latest Email
Send Email
Restore Point
Schedule Meeting
Next Meeting
Standby
Wake Up
Speed Test
Find File
Uptime
Weather Alert
Discord Message
Monitor Website
Check Website Changes
RSS Feed
Quote of the Day

🤝 Contributing

Pull requests are welcome! If you have ideas for new features, better error handling, or cross‑platform compatibility, feel free to open an issue or submit a PR. Please keep the code style consistent and test thoroughly.

📄 License

This project is licensed under the MIT License – see the LICENSE file for details.

⭐ Acknowledgements

- SpeechRecognition – Voice input
- edge-tts – High‑quality text‑to‑speech
- Groq – Lightning‑fast LLM inference
- OpenWeatherMap – Weather data
- DeepFace – Facial recognition
- Pygame – Audio playback
- PyAutoGUI – Keyboard/mouse automation
- Tesseract OCR – Screen text extraction

"Sometimes you gotta run before you can walk." – Tony Stark
