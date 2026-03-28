import { useEffect } from "react";

export interface ToastState {
    message: string;
    type: "success" | "error";
}

interface ToastProps {
    toast: ToastState;
    onClose: () => void;
}

const styles: Record<ToastState["type"], string> = {
    success: "border-green-200 bg-green-50 text-green-700",
    error: "border-red-200 bg-red-50 text-red-700",
};

export default function Toast({ toast, onClose }: ToastProps) {
    useEffect(() => {
        const timeoutId = window.setTimeout(() => {
            onClose();
        }, 3200);

        return () => {
            window.clearTimeout(timeoutId);
        };
    }, [onClose, toast.message, toast.type]);

    return (
        <div className="fixed right-6 top-6 z-[80] w-full max-w-sm">
            <div
                className={`rounded-2xl border px-4 py-3 text-sm font-medium shadow-lg ${styles[toast.type]}`}
                role={toast.type === "error" ? "alert" : "status"}
            >
                {toast.message}
            </div>
        </div>
    );
}
