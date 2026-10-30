# ORAI - Generative AI Studio

A modern, responsive, and state-of-the-art AI Image Generator web application powered by **Google Gemini**, **Pollinations FLUX**, and **Cloudflare Workers AI** (FLUX.1 Schnell) with auto-failover and multi-account rotation.

---

## 🌟 Features

- **FLUX.1 Schnell AI Generation:** Real-time text-to-image synthesis using Cloudflare Workers AI.
- **Style Selection:** Choose between 4 distinct styles:
  - 📷 **Realistic** (Photorealistic 8K photography, natural lighting)
  - ✨ **Anime** (Vibrant Japanese animation art style)
  - 🎬 **Cinematic** (35mm movie photography with dramatic lighting)
  - 🧊 **3D** (Octane 3D render with volumetric raytracing)
- **Size & Framing:**
  - 🔲 **Square (1:1)** — Balanced composition (avatars, square posts)
  - 🖼️ **Landscape (16:9)** — Cinematic widescreen framing
  - 📱 **Portrait (9:16)** — Tall vertical composition
- **Interactive Controls:**
  - 🎲 **Surprise Me** button with curated creative prompts
  - 💡 **Quick Prompt Pills** for one-click creative inspiration
  - ⏱️ **Live Generation Status** with elapsed timer & denoising phase updates
- **Image Showcase & Gallery:**
  - High-resolution preview with fullscreen lightbox inspection
  - Direct one-click image download (`.jpg`)
  - Session history gallery with quick download & prompt reuse
- **Secure Backend:**
  - Python Flask server managing Cloudflare API tokens securely through `.env`
  - Graceful error handling for API limits (429), authentication errors (401), and timeouts

---

## 📁 Project Structure

```text
d:\Ai\
├── backend\
│   ├── app.py                 # Flask REST API & static file server
│   ├── cloudflare_client.py   # Cloudflare Workers AI FLUX.1 client
│   ├── config.py              # Environment configuration loader
│   ├── requirements.txt       # Python dependencies
│   └── .env.example           # Backend environment template
├── frontend\
│   ├── index.html             # Clean semantic HTML5 layout
│   ├── css\
│   │   └── style.css          # Minimalist purple & blue design system
│   └── js\
│       └── app.js             # Generation state, gallery & API interaction
├── .env.example               # Root environment template
├── requirements.txt           # Root requirements
├── run.py                     # One-command application launcher
└── README.md                  # Documentation & setup guide
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- Python 3.9 or higher (tested on Python 3.14)
- A free or paid [Cloudflare account](https://dash.cloudflare.com/)

### 2. Install Dependencies
In your terminal, navigate to the project directory and install the required packages:

```bash
pip install -r requirements.txt
```

### 3. Configure Cloudflare API Credentials
Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Open `.env` and fill in your Cloudflare credentials:

```ini
CLOUDFLARE_ACCOUNT_ID=your_account_id_here
CLOUDFLARE_API_TOKEN=your_api_token_here
CLOUDFLARE_MODEL=@cf/black-forest-labs/flux-1-schnell
PORT=5000
```

#### How to get your Cloudflare credentials:
1. **Account ID**: Log in to [Cloudflare Dashboard](https://dash.cloudflare.com/). Click on any zone/domain or on your account home — your 32-character **Account ID** is on the right-hand sidebar.
2. **API Token**: Go to [Cloudflare API Tokens](https://dash.cloudflare.com/profile/api-tokens). Click **Create Token** &rarr; select **Workers AI** (or create a custom token granting `Account` &rarr; `Workers AI` &rarr; `Read` & `Edit`). Copy the token string.

### 4. Run the Application
Launch the server with a single command:

```bash
python run.py
```

Open your web browser and navigate to:
```
http://127.0.0.1:5000
```

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Serves the AI Image Studio Web UI |
| `GET` | `/api/status` | Checks if Cloudflare credentials are configured |
| `POST` | `/api/generate` | Generates image via FLUX.1 Schnell |

#### Sample Request Body to `/api/generate`:
```json
{
  "prompt": "A cybernetic samurai standing under neon rain",
  "style": "cinematic",
  "aspect_ratio": "landscape",
  "steps": 4
}
```

---

## 🛡️ Security
API tokens and Account IDs are never exposed to the client-side JavaScript. All API communication with Cloudflare is handled exclusively on the Python Flask backend.
