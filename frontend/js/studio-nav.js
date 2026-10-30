/**
 * Shared Studio Navigation & Shell Manager for AI Studio.
 * Handles sidebar rendering, user profile state, quota badges, and theme toggling.
 */

(function () {
  // Enforce authentication on all studio pages
  if (window.AIStudioAuth) {
    window.AIStudioAuth.requireAuth("/login");
  }

  // Restore preferred theme
  const savedTheme = localStorage.getItem("studio_theme") || "dark";
  document.documentElement.setAttribute("data-theme", savedTheme);

  // When DOM loads, initialize nav components
  document.addEventListener("DOMContentLoaded", () => {
    initThemeToggle();
    initMobileNav();
    initUserState();
    fetchUserQuotas();
  });

  function initThemeToggle() {
    const btn = document.getElementById("btn-theme-toggle");
    if (!btn) return;

    btn.addEventListener("click", () => {
      const current = document.documentElement.getAttribute("data-theme") || "dark";
      const next = current === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem("studio_theme", next);
      
      const icon = btn.querySelector("i");
      if (icon) {
        icon.setAttribute("data-lucide", next === "dark" ? "sun" : "moon");
        if (window.lucide) lucide.createIcons();
      }
    });
  }

  function initMobileNav() {
    const toggle = document.getElementById("mobile-nav-toggle");
    const sidebar = document.querySelector(".studio-sidebar");
    if (!toggle || !sidebar) return;

    toggle.addEventListener("click", () => {
      sidebar.classList.toggle("open");
    });

    document.addEventListener("click", (e) => {
      if (sidebar.classList.contains("open") && !sidebar.contains(e.target) && !toggle.contains(e.target)) {
        sidebar.classList.remove("open");
      }
    });
  }

  function initUserState() {
    if (!window.AIStudioAuth) return;

    window.AIStudioAuth.onStateChange((user) => {
      if (!user) return;

      const nameEl = document.getElementById("sidebar-user-name");
      const emailEl = document.getElementById("sidebar-user-email");
      const avatarEl = document.getElementById("sidebar-user-avatar");

      const displayName = user.displayName || user.email.split("@")[0] || "Creator";
      if (nameEl) nameEl.textContent = displayName;
      if (emailEl) emailEl.textContent = user.email;
      if (avatarEl) avatarEl.textContent = displayName.charAt(0).toUpperCase();
    });

    const logoutBtn = document.getElementById("btn-sidebar-logout");
    if (logoutBtn) {
      logoutBtn.addEventListener("click", async () => {
        if (confirm("Are you sure you want to log out of AI Studio?")) {
          await window.AIStudioAuth.logout();
        }
      });
    }
  }

  async function fetchUserQuotas() {
    try {
      const res = await window.AIStudioAuth.authFetch("/api/user/stats");
      if (res.ok) {
        const data = await res.json();
        const stats = data.stats || {};
        
        const imgChip = document.getElementById("quota-images");
        if (imgChip) {
          imgChip.innerHTML = `<i data-lucide="image"></i> <span><strong>${stats.image_remaining}</strong>/${stats.image_limit} Images Left</span>`;
        }

        const vidChip = document.getElementById("quota-videos");
        if (vidChip) {
          vidChip.innerHTML = `<i data-lucide="video"></i> <span><strong>${stats.video_remaining}</strong>/${stats.video_limit} Videos Left</span>`;
        }

        if (window.lucide) lucide.createIcons();
      }
    } catch (err) {
      console.warn("Could not fetch quotas:", err);
    }
  }

  // Export helper
  window.refreshQuotas = fetchUserQuotas;
})();
