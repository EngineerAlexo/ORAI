/**
 * AI Image Studio - Modern Minimalist Frontend Application
 * Interacts with Python Flask backend and Cloudflare Workers AI (FLUX.1 Schnell)
 */

document.addEventListener("DOMContentLoaded", () => {
  // -----------------------------------------------------------------
  // State
  // -----------------------------------------------------------------
  const state = {
    selectedStyle: "realistic",
    selectedRatio: "square",
    isGenerating: false,
    currentImage: null,
    apiConfigured: false,
    timerInterval: null,
    startTime: 0,
    gallery: [],
  };

  const STORAGE_KEY = "ai_image_studio_gallery_v1";

  // Creative inspiration prompts
  const INSPIRATION_PROMPTS = [
    "A majestic white owl perched on an ancient mossy tree, glowing bioluminescent mushrooms, misty enchanted forest, dramatic cinematic lighting, photorealistic 8k",
    "Futuristic neo-Tokyo street bathed in neon rain, purple and cyan reflections on wet asphalt, holographic billboards, cyberpunk aesthetics, sharp focus",
    "A cozy sunlit artisan coffee shop interior with monstera plants, steaming cappuccino with latte art, morning light rays, warm peaceful atmosphere",
    "An astronaut floating gracefully in deep space surrounded by a cosmic nebula with spiral galaxies, star dust, reflections on gold visor",
    "An adorable fluffy baby red panda wearing a tiny knitted woolen winter scarf, sitting on a snow-covered branch, gentle snowflakes falling",
    "Architectural masterpiece modern villa cantilevered over a dramatic ocean cliff at sunset, infinity pool, warm architectural lighting, minimalist luxury",
    "Mythical crystal dragon sleeping inside an amethyst geode cave, glowing crystals, ethereal purple and blue volumetric light, magical atmosphere",
    "Cyberpunk cybernetic samurai warrior with glowing katana, wearing ornate techwear armor in a dense neon rainstorm, cinematic depth of field",
    "Whimsical watercolor and ink village nestled in rolling green hills with flowering cherry blossom trees and winding cobblestone streets",
    "High fashion editorial portrait of a woman with vibrant floral crown, golden hour sunlight, soft natural freckles, 85mm lens portrait photography",
    "Steampunk airship soaring through golden cloud banks during a dramatic sunset, brass gears, steam exhausts, epic grand scale",
    "Vibrant tropical coral reef teeming with exotic glowing jellyfish, schools of sea turtles, turquoise crystal clear water, sun rays filtering down"
  ];

  // -----------------------------------------------------------------
  // DOM Elements
  // -----------------------------------------------------------------
  const el = {
    promptInput: document.getElementById("prompt-input"),
    charCount: document.getElementById("char-count"),
    btnSurprise: document.getElementById("btn-surprise"),
    btnClearPrompt: document.getElementById("btn-clear-prompt"),
    promptPills: document.getElementById("prompt-pills"),
    styleOptions: document.querySelectorAll("#style-options .option-card"),
    ratioOptions: document.querySelectorAll("#ratio-options .option-card"),
    btnGenerate: document.getElementById("btn-generate"),
    btnSpinner: document.getElementById("btn-spinner"),
    
    // Result sections
    resultSection: document.getElementById("result-section"),
    loadingCard: document.getElementById("loading-card"),
    loadingStatusText: document.getElementById("loading-status-text"),
    generationTimer: document.getElementById("generation-timer"),
    outputCard: document.getElementById("output-card"),
    generatedImage: document.getElementById("generated-image"),
    btnFullscreenView: document.getElementById("btn-fullscreen-view"),
    metaStyleText: document.getElementById("meta-style-text"),
    metaRatioText: document.getElementById("meta-ratio-text"),
    outputPromptDisplay: document.getElementById("output-prompt-display"),
    btnCopyPrompt: document.getElementById("btn-copy-prompt"),
    btnDownload: document.getElementById("btn-download"),
    btnGenerateAnother: document.getElementById("btn-generate-another"),
    
    // Error card
    errorCard: document.getElementById("error-card"),
    errorMessageText: document.getElementById("error-message-text"),
    errorHintText: document.getElementById("error-hint-text"),
    btnRetry: document.getElementById("btn-retry"),
    
    // Gallery
    galleryGrid: document.getElementById("gallery-grid"),
    galleryEmpty: document.getElementById("gallery-empty"),
    btnClearGallery: document.getElementById("btn-clear-gallery"),
    navGalleryCount: document.getElementById("nav-gallery-count"),
    
    // Status & Banners
    apiStatusBadge: document.getElementById("api-status-badge"),
    apiStatusText: document.getElementById("api-status-text"),
    missingCredentialsBanner: document.getElementById("missing-credentials-banner"),
    btnCloseBanner: document.getElementById("btn-close-banner"),
    btnOpenConfigGuide: document.getElementById("btn-open-config-guide"),
    btnApiModal: document.getElementById("btn-api-modal"),
    
    // Modals
    lightboxModal: document.getElementById("lightbox-modal"),
    lightboxImg: document.getElementById("lightbox-img"),
    lightboxPrompt: document.getElementById("lightbox-prompt"),
    lightboxDownload: document.getElementById("btn-lightbox-download"),
    btnCloseLightbox: document.getElementById("btn-close-lightbox"),
    
    apiModal: document.getElementById("api-modal"),
    btnCloseApiModal: document.getElementById("btn-close-api-modal"),
    btnDoneModal: document.getElementById("btn-done-modal"),
    btnRefreshStatus: document.getElementById("btn-refresh-status"),
  };

  // -----------------------------------------------------------------
  // Initialize
  // -----------------------------------------------------------------
  function init() {
    initLucide();
    loadGalleryFromStorage();
    checkApiStatus();
    setupEventListeners();
  }

  function initLucide() {
    if (window.lucide && typeof window.lucide.createIcons === "function") {
      window.lucide.createIcons();
    }
  }

  // -----------------------------------------------------------------
  // API Status & Configuration Check
  // -----------------------------------------------------------------
  async function checkApiStatus() {
    try {
      const res = await fetch("/api/status");
      if (!res.ok) throw new Error("Status check failed");
      
      const data = await res.json();
      state.apiConfigured = Boolean(data.configured);

      if (state.apiConfigured) {
        el.apiStatusBadge.className = "status-indicator-dot";
        el.apiStatusBadge.title = `ORAI Engine Online (${data.model})`;
        el.missingCredentialsBanner.classList.add("hidden");
      } else {
        el.apiStatusBadge.className = "status-indicator-dot status-warning";
        el.apiStatusBadge.title = "Cloudflare credentials not configured in .env";
        el.missingCredentialsBanner.classList.remove("hidden");
      }
    } catch (err) {
      console.warn("Failed to check backend API status:", err);
      el.apiStatusBadge.className = "status-indicator-dot status-warning";
      el.apiStatusBadge.title = "Backend Offline";
    }
  }

  // -----------------------------------------------------------------
  // Event Listeners
  // -----------------------------------------------------------------
  function setupEventListeners() {
    // Character counter
    el.promptInput.addEventListener("input", () => {
      el.charCount.textContent = el.promptInput.value.length;
    });

    // Surprise Me
    el.btnSurprise.addEventListener("click", () => {
      const randomPrompt = INSPIRATION_PROMPTS[Math.floor(Math.random() * INSPIRATION_PROMPTS.length)];
      el.promptInput.value = randomPrompt;
      el.charCount.textContent = randomPrompt.length;
      el.promptInput.focus();
    });

    // Clear prompt
    el.btnClearPrompt.addEventListener("click", () => {
      el.promptInput.value = "";
      el.charCount.textContent = "0";
      el.promptInput.focus();
    });

    // Suggestion pills
    el.promptPills.addEventListener("click", (e) => {
      const pill = e.target.closest(".pill-btn");
      if (pill && pill.dataset.prompt) {
        el.promptInput.value = pill.dataset.prompt;
        el.charCount.textContent = el.promptInput.value.length;
        el.promptInput.focus();
      }
    });

    // Style selector cards
    el.styleOptions.forEach((card) => {
      card.addEventListener("click", () => {
        el.styleOptions.forEach((c) => c.classList.remove("active"));
        card.classList.add("active");
        state.selectedStyle = card.dataset.style;
      });
    });

    // Aspect ratio selector cards
    el.ratioOptions.forEach((card) => {
      card.addEventListener("click", () => {
        el.ratioOptions.forEach((c) => c.classList.remove("active"));
        card.classList.add("active");
        state.selectedRatio = card.dataset.ratio;
      });
    });

    // Generate button
    el.btnGenerate.addEventListener("click", handleGenerate);

    // Enter key shortcut (Ctrl + Enter)
    el.promptInput.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        handleGenerate();
      }
    });

    // Download action
    el.btnDownload.addEventListener("click", () => {
      if (state.currentImage) {
        downloadImage(state.currentImage.image, `flux-art-${Date.now()}.jpg`);
      }
    });

    // Generate another button
    el.btnGenerateAnother.addEventListener("click", () => {
      window.scrollTo({ top: el.promptInput.getBoundingClientRect().top + window.scrollY - 100, behavior: "smooth" });
      el.promptInput.focus();
      el.promptInput.select();
    });

    // Copy prompt
    el.btnCopyPrompt.addEventListener("click", async () => {
      if (state.currentImage && state.currentImage.prompt) {
        try {
          await navigator.clipboard.writeText(state.currentImage.prompt);
          const origText = el.btnCopyPrompt.innerHTML;
          el.btnCopyPrompt.innerHTML = `<i data-lucide="check"></i> <span>Copied!</span>`;
          initLucide();
          setTimeout(() => {
            el.btnCopyPrompt.innerHTML = origText;
            initLucide();
          }, 2000);
        } catch (err) {
          console.error("Clipboard copy failed:", err);
        }
      }
    });

    // Retry button on error
    el.btnRetry.addEventListener("click", handleGenerate);

    // Fullscreen lightbox view
    if (el.btnFullscreenView) {
      el.btnFullscreenView.addEventListener("click", () => {
        if (state.currentImage) {
          openLightbox(state.currentImage.image, state.currentImage.prompt);
        }
      });
    }

    // Direct click on generated image opens fullscreen lightbox
    if (el.generatedImage) {
      el.generatedImage.addEventListener("click", () => {
        if (state.currentImage) {
          openLightbox(state.currentImage.image, state.currentImage.prompt);
        }
      });
    }

    const outputImgWrapper = document.getElementById("output-image-wrapper");
    if (outputImgWrapper) {
      outputImgWrapper.addEventListener("click", (e) => {
        if (state.currentImage && !e.target.closest("button")) {
          openLightbox(state.currentImage.image, state.currentImage.prompt);
        }
      });
    }

    // Close lightbox
    el.btnCloseLightbox.addEventListener("click", closeLightbox);
    el.lightboxModal.addEventListener("click", (e) => {
      if (e.target === el.lightboxModal) closeLightbox();
    });

    // Lightbox download
    el.lightboxDownload.addEventListener("click", () => {
      if (state.currentImage) {
        downloadImage(state.currentImage.image, `flux-art-${Date.now()}.jpg`);
      }
    });

    // API Modal Handlers
    if (el.btnApiModal) el.btnApiModal.addEventListener("click", openApiModal);
    el.btnOpenConfigGuide.addEventListener("click", openApiModal);
    el.btnCloseBanner.addEventListener("click", () => el.missingCredentialsBanner.classList.add("hidden"));
    el.btnCloseApiModal.addEventListener("click", closeApiModal);
    el.btnDoneModal.addEventListener("click", closeApiModal);
    el.apiModal.addEventListener("click", (e) => {
      if (e.target === el.apiModal) closeApiModal();
    });

    el.btnRefreshStatus.addEventListener("click", async () => {
      await checkApiStatus();
      if (state.apiConfigured) {
        closeApiModal();
      }
    });

    // Clear gallery history
    el.btnClearGallery.addEventListener("click", () => {
      if (!state.gallery.length) return;
      if (confirm("Are you sure you want to clear your generated images history?")) {
        state.gallery = [];
        saveGalleryToStorage();
        renderGallery();
      }
    });
  }

  // -----------------------------------------------------------------
  // Image Generation Handler
  // -----------------------------------------------------------------
  async function handleGenerate() {
    const promptText = el.promptInput.value.trim();
    if (!promptText) {
      alert("Please enter a prompt describing the image you want to create.");
      el.promptInput.focus();
      return;
    }

    if (state.isGenerating) return;

    // Start generation state
    setGeneratingState(true);

    // Scroll smoothly to result section
    el.resultSection.classList.remove("hidden");
    el.loadingCard.classList.remove("hidden");
    el.outputCard.classList.add("hidden");
    el.errorCard.classList.add("hidden");

    el.resultSection.scrollIntoView({ behavior: "smooth", block: "nearest" });

    // Loading progress messages
    startTimer();

    try {
      const response = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: promptText,
          style: state.selectedStyle,
          aspect_ratio: state.selectedRatio,
          steps: 4,
        }),
      });

      const data = await response.json();
      stopTimer();

      if (!response.ok || !data.success) {
        showError(data.error || "Failed to generate image.", data.code);
        return;
      }

      // Success
      const imageRecord = {
        id: "img_" + Date.now(),
        image: data.image,
        prompt: promptText,
        enhanced_prompt: data.enhanced_prompt,
        style: state.selectedStyle,
        aspect_ratio: state.selectedRatio,
        provider: data.provider || "ORAI Engine",
        timestamp: new Date().toISOString(),
      };

      state.currentImage = imageRecord;
      showSuccess(imageRecord);

      // Add to gallery
      addToGallery(imageRecord);

    } catch (err) {
      stopTimer();
      showError(
        "Could not connect to the image generation server. Please make sure the Flask backend is running.",
        "NETWORK_ERROR"
      );
    } finally {
      setGeneratingState(false);
    }
  }

  function setGeneratingState(generating) {
    state.isGenerating = generating;
    el.btnGenerate.disabled = generating;
    if (generating) {
      el.btnSpinner.classList.remove("hidden");
      el.btnGenerate.querySelector(".btn-icon").classList.add("hidden");
      el.btnGenerate.querySelector(".btn-text").textContent = "Synthesizing with ORAI...";
    } else {
      el.btnSpinner.classList.add("hidden");
      el.btnGenerate.querySelector(".btn-icon").classList.remove("hidden");
      el.btnGenerate.querySelector(".btn-text").textContent = "Generate with ORAI";
    }
  }

  // -----------------------------------------------------------------
  // Timer & Progress Messages
  // -----------------------------------------------------------------
  function startTimer() {
    state.startTime = Date.now();
    el.generationTimer.textContent = "Elapsed: 0.0s";
    el.loadingStatusText.textContent = "Connecting to ORAI Engine...";

    if (state.timerInterval) clearInterval(state.timerInterval);

    state.timerInterval = setInterval(() => {
      const elapsed = ((Date.now() - state.startTime) / 1000).toFixed(1);
      el.generationTimer.textContent = `Elapsed: ${elapsed}s`;

      const sec = parseFloat(elapsed);
      if (sec < 2.0) {
        el.loadingStatusText.textContent = "Synthesizing latents with ORAI...";
      } else if (sec < 4.5) {
        el.loadingStatusText.textContent = "Refining composition, lighting, and textures...";
      } else if (sec < 7.0) {
        el.loadingStatusText.textContent = "Denoising pixels and finalizing image output...";
      } else {
        el.loadingStatusText.textContent = "Almost ready, transferring image bytes...";
      }
    }, 100);
  }

  function stopTimer() {
    if (state.timerInterval) {
      clearInterval(state.timerInterval);
      state.timerInterval = null;
    }
  }

  // -----------------------------------------------------------------
  // Display States
  // -----------------------------------------------------------------
  function getRatioClass(ratio) {
    const r = (ratio || "").toLowerCase().trim();
    if (r === "landscape" || r === "16:9" || r === "16-9") return "ratio-16-9";
    if (r === "portrait" || r === "9:16" || r === "9-16") return "ratio-9-16";
    return "ratio-1-1";
  }

  function showSuccess(imageRecord) {
    el.loadingCard.classList.add("hidden");
    el.errorCard.classList.add("hidden");
    el.outputCard.classList.remove("hidden");

    const previewWrapper = document.getElementById("output-image-wrapper");
    if (previewWrapper) {
      previewWrapper.className = `output-preview-container ${getRatioClass(imageRecord.aspect_ratio)}`;
    }

    el.generatedImage.src = imageRecord.image;
    el.metaStyleText.textContent = capitalize(imageRecord.style);
    el.metaRatioText.textContent = getRatioLabel(imageRecord.aspect_ratio);
    el.outputPromptDisplay.textContent = imageRecord.prompt;

    const metaEngineText = document.getElementById("meta-engine-text");
    if (metaEngineText) {
      metaEngineText.textContent = imageRecord.provider || "ORAI Engine";
    }

    initLucide();
  }

  function showError(message, code) {
    el.loadingCard.classList.add("hidden");
    el.outputCard.classList.add("hidden");
    el.errorCard.classList.remove("hidden");

    el.errorMessageText.textContent = message;

    // Helpful resolution hints based on error codes
    let hint = "";
    if (code === "MISSING_CREDENTIALS") {
      hint = "Tip: Open your .env file and paste your Cloudflare Account ID and API Token.";
    } else if (code === "INVALID_TOKEN") {
      hint = "Tip: Verify that your API Token has 'Workers AI' Read/Edit permissions in Cloudflare.";
    } else if (code === "RATE_LIMIT_EXCEEDED") {
      hint = "Tip: Cloudflare Workers AI free tier allows a generous daily limit. Please wait a minute and retry.";
    } else if (code === "REQUEST_TIMEOUT") {
      hint = "Tip: The request took too long. Cloudflare may be under temporary load. Try again.";
    }
    el.errorHintText.textContent = hint;

    initLucide();
  }

  // -----------------------------------------------------------------
  // Gallery Management
  // -----------------------------------------------------------------
  function addToGallery(imageRecord) {
    // Keep most recent first, limit to 24 images to avoid exceeding localStorage quota
    state.gallery.unshift(imageRecord);
    if (state.gallery.length > 24) {
      state.gallery = state.gallery.slice(0, 24);
    }
    saveGalleryToStorage();
    renderGallery();
  }

  function renderGallery() {
    el.navGalleryCount.textContent = state.gallery.length;

    if (!state.gallery.length) {
      el.galleryGrid.innerHTML = "";
      el.galleryEmpty.classList.remove("hidden");
      el.btnClearGallery.classList.add("hidden");
      return;
    }

    el.galleryEmpty.classList.add("hidden");
    el.btnClearGallery.classList.remove("hidden");

    el.galleryGrid.innerHTML = state.gallery
      .map((item) => {
        const ratioClass = getRatioClass(item.aspect_ratio);
        return `
        <div class="gallery-card" data-id="${item.id}">
          <div class="gallery-thumb-wrap ${ratioClass}" onclick="window.viewGalleryItem('${item.id}')">
            <img class="gallery-thumb" src="${item.image}" alt="${escapeHtml(item.prompt)}" loading="lazy" />
            <div class="gallery-thumb-overlay">
              <div class="overlay-view-icon">
                <i data-lucide="maximize-2"></i>
              </div>
            </div>
          </div>
          <div class="gallery-content">
            <div class="gallery-card-meta">
              <span class="meta-tag badge-style">${capitalize(item.style)}</span>
              <span class="meta-tag">${getRatioLabel(item.aspect_ratio)}</span>
            </div>
            <p class="gallery-prompt" title="${escapeHtml(item.prompt)}">${escapeHtml(item.prompt)}</p>
            <div class="gallery-card-actions">
              <button type="button" class="gallery-action-btn" onclick="window.downloadGalleryItem('${item.id}')">
                <i data-lucide="download"></i>
                <span>Save</span>
              </button>
              <button type="button" class="gallery-action-btn btn-use-prompt" onclick="window.reusePrompt('${item.id}')">
                <i data-lucide="sparkles"></i>
                <span>Use Prompt</span>
              </button>
            </div>
          </div>
        </div>
      `;
      })
      .join("");

    initLucide();
  }

  function saveGalleryToStorage() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state.gallery));
    } catch (err) {
      console.warn("Storage quota exceeded or storage unavailable:", err);
    }
  }

  function loadGalleryFromStorage() {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        state.gallery = JSON.parse(saved);
      }
    } catch (err) {
      state.gallery = [];
    }
    renderGallery();
  }

  // Window global hooks for inline onclick handlers
  window.viewGalleryItem = (id) => {
    const item = state.gallery.find((g) => g.id === id);
    if (item) {
      openLightbox(item.image, item.prompt);
    }
  };

  window.downloadGalleryItem = (id) => {
    const item = state.gallery.find((g) => g.id === id);
    if (item) {
      downloadImage(item.image, `flux-art-${id}.jpg`);
    }
  };

  window.reusePrompt = (id) => {
    const item = state.gallery.find((g) => g.id === id);
    if (item) {
      el.promptInput.value = item.prompt;
      el.charCount.textContent = item.prompt.length;

      // Select style
      if (item.style) {
        el.styleOptions.forEach((card) => {
          if (card.dataset.style === item.style) {
            card.click();
          }
        });
      }

      // Scroll to prompt box
      window.scrollTo({ top: el.promptInput.getBoundingClientRect().top + window.scrollY - 100, behavior: "smooth" });
      el.promptInput.focus();
    }
  };

  // -----------------------------------------------------------------
  // Modals & Helpers
  // -----------------------------------------------------------------
  function openLightbox(imgSrc, prompt) {
    el.lightboxImg.src = imgSrc;
    el.lightboxPrompt.textContent = prompt || "";
    el.lightboxModal.classList.remove("hidden");
    document.body.style.overflow = "hidden";
    initLucide();
  }

  function closeLightbox() {
    el.lightboxModal.classList.add("hidden");
    document.body.style.overflow = "";
  }

  function openApiModal() {
    el.apiModal.classList.remove("hidden");
    document.body.style.overflow = "hidden";
    initLucide();
  }

  function closeApiModal() {
    el.apiModal.classList.add("hidden");
    document.body.style.overflow = "";
  }

  function downloadImage(dataUrl, filename) {
    const link = document.createElement("a");
    link.href = dataUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  function capitalize(str) {
    if (!str) return "";
    return str.charAt(0).toUpperCase() + str.slice(1);
  }

  function getRatioLabel(ratio) {
    const r = (ratio || "").toLowerCase().trim();
    if (r === "landscape" || r === "16:9" || r === "16-9") return "Landscape (16:9)";
    if (r === "portrait" || r === "9:16" || r === "9-16") return "Portrait (9:16)";
    return "Square (1:1)";
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  // Launch application
  init();
});
