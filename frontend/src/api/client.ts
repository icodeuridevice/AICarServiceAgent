import axios from "axios";

const apiClient = axios.create({
    baseURL: "http://127.0.0.1:8000",
    headers: {
        "Content-Type": "application/json",
    },
});

// ── Auth interceptor ─────────────────────────────────────────────────
// Reads the JWT from localStorage on every request and attaches it
// as a Bearer token in the Authorization header.
apiClient.interceptors.request.use((config) => {
    const token = localStorage.getItem("access_token");
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

export default apiClient;
