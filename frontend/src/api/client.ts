import axios from "axios";
import { getToken, clearToken } from "../auth/auth";

const apiClient = axios.create({
    baseURL: "http://127.0.0.1:8000",
    headers: {
        "Content-Type": "application/json",
    },
});

// ── Auth Request Interceptor ──────────────────────────────────────────
apiClient.interceptors.request.use((config) => {
    const token = getToken();
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

// ── Auth Response Interceptor ─────────────────────────────────────────
apiClient.interceptors.response.use(
    (response) => {
        return response;
    },
    (error) => {
        if (error.response && error.response.status === 401) {
            clearToken();
            // Use window.location.href to avoid infinite loop when clearing session
            // and ensure a strict reload from the unauthenticated state.
            if (window.location.pathname !== "/login") {
                window.location.href = "/login";
            }
        }
        return Promise.reject(error);
    }
);

export default apiClient;
