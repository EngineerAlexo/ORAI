/**
 * Firebase Configuration & Authentication Helper for AI Studio.
 * Uses Firebase v9/v10 Compat SDK for maximum browser compatibility.
 */

// User Firebase configuration from save-data-19a24
const firebaseConfig = {
  apiKey: "AIzaSyDG_QswQHzv8d4kpmPF2gYNimhgZhTLz1Q",
  authDomain: "save-data-19a24.firebaseapp.com",
  projectId: "save-data-19a24",
  storageBucket: "save-data-19a24.firebasestorage.app",
  messagingSenderId: "240569425778",
  appId: "1:240569425778:web:fe8e24f82f29dbce9c07eb"
};

// Initialize Firebase
if (!firebase.apps.length) {
  firebase.initializeApp(firebaseConfig);
}

const auth = firebase.auth();
auth.setPersistence(firebase.auth.Auth.Persistence.LOCAL);

/**
 * Get the current Firebase ID token.
 */
async function getAuthToken(forceRefresh = false) {
  const user = auth.currentUser;
  if (!user) return null;
  try {
    return await user.getIdToken(forceRefresh);
  } catch (err) {
    console.error("Error retrieving Firebase token:", err);
    return null;
  }
}

/**
 * Fetch wrapper that automatically attaches Firebase Authorization header.
 */
async function authFetch(url, options = {}) {
  let targetUrl = url;
  if (url.startsWith("/") && window.location.protocol === "file:") {
    targetUrl = "http://127.0.0.1:5000" + url;
  }

  const token = await getAuthToken();
  const headers = options.headers ? { ...options.headers } : {};

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  // Set default JSON Content-Type if body is string
  if (options.body && typeof options.body === "string" && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(targetUrl, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    console.warn("API returned 401 (unauthenticated). Continuing in guest mode.");
  }

  return response;
}

/**
 * Global User State Management
 */
window.AIStudioAuth = {
  auth,
  getAuthToken,
  authFetch,

  // Register
  async register(fullName, email, password) {
    const cred = await auth.createUserWithEmailAndPassword(email, password);
    if (cred.user && fullName) {
      await cred.user.updateProfile({ displayName: fullName });
      try {
        await cred.user.sendEmailVerification();
      } catch (ve) {
        console.warn("Email verification send note:", ve);
      }
    }
    return cred.user;
  },

  // Login
  async login(email, password) {
    const cred = await auth.signInWithEmailAndPassword(email, password);
    return cred.user;
  },

  // Forgot password
  async resetPassword(email) {
    return await auth.sendPasswordResetEmail(email);
  },

  // Logout
  async logout() {
    await auth.signOut();
    localStorage.removeItem("studio_user_cache");
    window.location.href = "/login";
  },

  // Auth observer
  onStateChange(callback) {
    return auth.onAuthStateChanged((user) => {
      callback(user);
    });
  },

  // Route protector for studio pages
  requireAuth(redirectUrl = "/login") {
    auth.onAuthStateChanged((user) => {
      if (!user) {
        sessionStorage.setItem("auth_redirect", window.location.pathname);
        window.location.href = redirectUrl;
      }
    });
  },

  // Route protector for guest pages (login/register)
  redirectIfAuthenticated(redirectUrl = "/dashboard") {
    auth.onAuthStateChanged((user) => {
      if (user) {
        const dest = sessionStorage.getItem("auth_redirect") || redirectUrl;
        sessionStorage.removeItem("auth_redirect");
        window.location.href = dest;
      }
    });
  }
};
