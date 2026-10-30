# AI Studio &mdash; AI Image & Video Studio

A professional, state-of-the-art **AI Image and Video Studio** built with a Python Flask REST backend, responsive glassmorphic frontend, and complete **Firebase Authentication & Firestore** integration.

---

## 🌟 Key Features

### 1. 🔐 User Authentication (Firebase Auth)
- **Account Registration & Login:** Full Name, Email, Password, Confirmation.
- **Session Security:** Cryptographic Firebase ID Token verification on Flask backend (`@require_auth`).
- **User Isolation:** Every user has their own private gallery and daily usage statistics.
- **Password Reset:** Automated password reset links via email.
- **Route Protection:** Protected API endpoints and automatic redirection for visitors.

### 2. 🎨 AI Image Studio (Multi-Provider Priority)
- **Engine Priority Order:**
  1. **Cloudflare Workers AI** (FLUX.1 Schnell with 5-Account auto-rotation on rate limits)
  2. **Google Gemini Image API** (`gemini-2.5-flash-image` / `imagen-3.0`)
  3. **Pollinations FLUX Turbo** (Priority authenticated pipeline with native high-res)
- **7 Artistic Styles:** Realistic 8K, Cinematic 35mm, Anime, 3D Render, Digital Art, Fantasy, Wildlife Photography.
- **Aspect Ratio Composition:**
  - `1:1` Square (1024×1024)
  - `16:9` Landscape (1024×576 with Rule-of-Thirds headroom preservation)
  - `9:16` Portrait (576×1024)
  - `4:3` Standard Photo (1024×768)
- **Negative Prompting:** Avoid unwanted artifacts, extra limbs, or low quality.
- **Interactive Inspection:** Clickable preview with fullscreen lightbox inspection and instant JPEG download.

### 3. 🎬 AI Video Studio (Text-to-Video & Image-to-Video)
- **Text-to-Video (T2V):** Synthesize dynamic video clips directly from text descriptions.
- **Image-to-Video (I2V):** Upload any still image to animate motion, camera movement, and action.
- **Asynchronous Processing:** Non-blocking background worker queues with real-time progress polling.
- **Real Video Player:** Built-in HTML5 video player with MP4 download.
- **Modular Provider Support:** Ready for Hugging Face Router, ModelsLab, Runware, and Replicate video endpoints.

### 4. 📁 Personal Cloud Gallery
- **Isolated User Storage:** Users only see media they generated.
- **Media Tabs:** Filter between All Media, Images, and Videos.
- **One-Click Management:** Quick download, full-screen playback/preview, and permanent deletion.

### 5. ⏱️ Usage Quotas & Limits
- Configurable per-user daily limits (default: **25 images/day** and **10 videos/day**).
- Real-time quota pills in topbar showing remaining daily credits.

---

## 📁 Project Architecture

```text
D:\Ai\
├── backend\
│   ├── app.py                  # Flask REST API & static file server
│   ├── config.py               # Configuration loader & quota settings
│   ├── auth_middleware.py      # Firebase ID token verification middleware
│   ├── firebase_service.py     # Firebase Admin & Google Identity REST verifier
│   ├── image_generator.py      # Image generator coordinator & cropping logic
│   ├── video_generator.py      # Asynchronous video synthesis queue & polling
│   ├── cloudflare_client.py    # Cloudflare 5-account pool & provider failover
│   ├── storage_manager.py      # Media storage & user gallery indexing
│   ├── usage_manager.py        # Daily usage quotas & statistics tracking
│   ├── requirements.txt        # Backend dependencies
│   └── uploads\                # User-isolated images and videos storage
├── frontend\
│   ├── index.html              # Public Landing Portal
│   ├── login.html              # Sign In & Password Reset page
│   ├── register.html           # Account Registration page
│   ├── dashboard.html          # Studio Overview & Quick Actions
│   ├── image-generator.html    # Full AI Image Generation Studio
│   ├── video-generator.html    # AI Video Generation Studio (T2V & I2V)
│   ├── gallery.html            # Personal User Gallery
│   ├── account.html            # Profile, Quotas & API Status
│   ├── css\
│   │   ├── style.css           # Core dark glassmorphism system
│   │   └── studio.css          # Studio sidebar, video player, and layout
│   └── js\
│       ├── firebase-config.js  # Firebase SDK configuration & authFetch helper
│       ├── studio-nav.js       # Shared studio sidebar & quota updater
│       └── app.js              # Legacy interactive helpers
├── .env                        # Private environment variables (Git-ignored)
├── .env.example                # Configuration template
├── .gitignore                  # Security protection
├── requirements.txt            # Top-level dependencies
├── run.py                      # Application launcher
└── README.md                   # Platform documentation
```

---

## 🚀 Quick Setup Guide

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment (`.env`)
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Fill in your API tokens:
- **Cloudflare Accounts:** `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` (up to 5 accounts supported for auto-rotation)
- **Pollinations API Key:** `POLLINATIONS_API_KEY` (for Priority Turbo FLUX)
- **Google Gemini API Key:** `GEMINI_API_KEY` (optional)
- **Firebase Configuration:** Pre-configured with user project `save-data-19a24`.

### 3. Start the Server
```bash
python run.py
```
Open your browser at:
```
http://127.0.0.1:5000
```

---

## 🛡️ Security Best Practices
- **No Client-Side Secrets:** Secret keys for Cloudflare, Gemini, and Pollinations are strictly confined to the backend and never exposed to browser JavaScript.
- **Server-Side Token Verification:** All generation requests require a valid, non-expired Firebase ID token in the `Authorization: Bearer <token>` header.
- **Quota Protection:** Server-side quota checks prevent unauthorized credit consumption.
