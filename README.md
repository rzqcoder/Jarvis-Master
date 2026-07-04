Jarvis-Master

A voice-controlled Windows desktop assistant for automating your computer with natural language. The app integrates speech recognition, LLaMA 3.3 (using Groq), screen OCR, and automation libraries into a single Python program.
Warning: This script controls your keyboard and mouse and can potentially cause unintended actions. It is highly recommended to review the code before executing it.

Key Features

Voice Command: Respond to "Jarvis," "Computer," "Sir," or "Boss." Includes a seamless "Two-Way Conversation" mode for dynamic interaction.
Instant Scripting: Command Jarvis to "write a script to monitor CPU," and it will generate and execute Python code in real-time.

On-Screen Awareness: Analyze and interact with content directly from your screen. Read text, click specific elements, and perform basic UI actions.
System Automation: Effortlessly manage your system, including adjusting volume, snapping windows, launching applications, tracking vital stats, and executing custom macros.
Seamless Integrations: Access Google Calendar events, retrieve information from your Gmail inbox, and send alerts via Discord webhooks.

Getting Started

1. Prerequisites

* Windows OS and Python 3.10+

* Tesseract OCR (install to C:\Program Files\Tesseract-OCR\tesseract.exe)

* Functional microphone.

2. Installation

Bash

git clone https://github.com/yourusername/jarvis-assistant.git

cd jarvis-assistant

python -m venv venv

venv\Scripts\activate

pip install -r requirements.txt

3. Configuration

* Create an authorized_users/ directory and place a picture of yourself named tony.jpg for facial recognition.

* Rename .env.example to .env and input your API keys:

Ini, TOML

GROQAPIKEY=yourgroqkey

WEATHERAPIKEY=yourweatherkey

EMAILADDRESS=yourgmail@gmail.com

EMAILPASSWORD=yourgmailapppassword

4. Running the Assistant

Bash

python jarvis.py

Sample Voice Commands

"Morning report" - Get a summary of weather and daily news.
"Vitals" - Request a report on current CPU, GPU, and RAM usage.
"Read the screen" - Jarvis will read and summarize all visible text.
"Snap left" - Move the current window to the left side of the screen.
"Kill all" - Close all major open applications instantly.

Open App, Close Window, Create Script, Run Script, Volume Up/Down, Mute, Save Clipboard, Send Email, Next Meeting, Work Mode, Gaming Mode, Remember [Fact], Recall.

License: MIT. Built with Groq, DeepFace, PyAutoGUI, and Tesseract.
