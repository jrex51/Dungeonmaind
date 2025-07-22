# 🧠 Dungeon M-AI-nd

> Transcribe, search, and query your **Dungeons & Dragons** sessions – locally and private, with AI support.

**Dungeon M-AI-nd** ist eine lokal laufende Software zur Analyse von DnD-Kampagnen. Sie nimmt Sprachaufzeichnungen auf, transkribiert sie automatisch, speichert die Inhalte durchsuchbar und ermöglicht es dir, im Verlauf deiner Kampagne Fragen zu früheren Ereignissen zu stellen – ganz ohne Cloud-Anbindung.

---

## 🗺️ Projektziel

Das Ziel ist es, DnD-Sitzungen effizient aufzuzeichnen und durchsuchbar zu machen. Spieler:innen sollen jederzeit Fragen wie:

- *"Was ist mit dem magischen Dolch passiert?"*
- *"Was hat der NSC gesagt, bevor wir die Stadt verließen?"*

stellen können – und erhalten eine Antwort basierend auf echten Transkriptionen der Spielrunde.

---

## ⚙️ Funktionen

### ✅ Bereits umgesetzt
- [x] Sprachaufnahme über das Frontend (in Arbeit)
- [x] Transkription mittels WhisperX
- [x] Speicherung transkribierter Texte in einer Vektordatenbank
- [x] Anbindung eines lokalen LLM zur Beantwortung von Fragen

### 🔜 Geplant
- [ ] Intuitive Web-Oberfläche (Vue + TypeScript)
- [ ] Export- und Archivierungsfunktion für Kampagnen
- [ ] Offline-Modus für Laptops/Tablets auf Spieltischen
- [ ] Charakter-, Ort- und Ereignis-Tracking

---

## 🧑‍💻 Systemübersicht

🎙️ Aufnahme → 🧠 Transkription (WhisperX) 
→ 🧩 Embedding → 💾 Speicherung → 🤖 Frage/Antwort via LLM

---

## 📦 Installation

### Voraussetzungen
- Python 3.11
- Git
- (Optional) GPU mit CUDA für beschleunigte Transkription
- ffmpeg (für WhisperX)
  
### 1. Repository klonen
```text
git clone https://github.com/FNitzsche/Dungeonmaind.git
cd Dungeonmaind
```

### 2. Python-Umgebung einrichten
```text
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```


### 3. ...

___

## 💬 Nutzung

### Sitzung aufzeichnen
1. Starte die Frontend-App (npm run dev – noch in Entwicklung).
2. Klicke auf „Aufnahme starten“.
3. Audio wird an das Backend gesendet, transkribiert und gespeichert.

### Fragen stellen
Über das Web-Frontend kannst du Fragen wie:
```text
"Was geschah in der Taverne?"
```
stellen – das LLM antwortet auf Basis der gespeicherten Transkripte.


