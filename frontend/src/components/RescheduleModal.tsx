import { useState } from "react";
import axios from "axios";
import { rescheduleBooking } from "../api/bookings";
import ErrorBanner from "./ErrorBanner";

interface RescheduleModalProps {
    bookingId: number;
    currentDate: string;
    onClose: () => void;
    onSuccess: () => void;
}

const toInputDate = (date: string): string => {
    return date.slice(0, 10);
};

const DATE_ONLY_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

const getApiErrorMessage = (err: unknown): string => {
    if (!axios.isAxiosError(err)) {
        if (err instanceof Error && err.message) {
            return err.message;
        }
        return "Failed to reschedule booking.";
    }

    const domainMessage = err.response?.data?.error?.message as unknown;
    if (typeof domainMessage === "string" && domainMessage.trim()) {
        return domainMessage;
    }

    const detail = err.response?.data?.detail as unknown;

    if (typeof detail === "string" && detail.trim()) {
        return detail;
    }

    if (Array.isArray(detail) && detail.length > 0) {
        const first = detail[0] as { msg?: unknown } | undefined;
        if (first && typeof first.msg === "string" && first.msg.trim()) {
            return first.msg;
        }
    }

    if (typeof err.message === "string" && err.message.trim()) {
        return err.message;
    }

    return "Failed to reschedule booking.";
};

export default function RescheduleModal({
    bookingId,
    currentDate,
    onClose,
    onSuccess,
}: RescheduleModalProps) {
    const [newDate, setNewDate] = useState<string>(toInputDate(currentDate));
    const [loading, setLoading] = useState<boolean>(false);
    const [error, setError] = useState<string>("");

    const handleConfirm = async () => {
        if (!newDate) {
            setError("Please select a date.");
            return;
        }

        if (!DATE_ONLY_PATTERN.test(newDate)) {
            setError("Date must be in YYYY-MM-DD format.");
            return;
        }

        try {
            setLoading(true);
            setError("");
            const formattedDate = newDate;
            await rescheduleBooking(
                Number(bookingId),
                formattedDate
            );
            onClose();
            onSuccess();
        } catch (err: unknown) {
            setError(getApiErrorMessage(err));
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black bg-opacity-40 flex items-center justify-center">
            <div className="bg-white rounded-md p-6 w-96">
                <h2 className="text-lg font-semibold text-gray-900">Reschedule Booking</h2>
                <div className="mt-4">
                    <label className="block text-sm text-gray-700 mb-2" htmlFor="reschedule-date">
                        New Date
                    </label>
                    <input
                        id="reschedule-date"
                        className="w-full border rounded px-3 py-2 text-sm"
                        type="date"
                        value={newDate}
                        onChange={(event) => setNewDate(event.target.value)}
                    />
                </div>
                {error && (
                    <div className="mt-3">
                        <ErrorBanner message={error} />
                    </div>
                )}
                <div className="mt-5 flex justify-end gap-2">
                    <button
                        className="px-3 py-1 rounded border text-sm text-gray-700 hover:bg-gray-100"
                        type="button"
                        onClick={onClose}
                        disabled={loading}
                    >
                        Cancel
                    </button>
                    <button
                        className="px-3 py-1 rounded bg-gray-800 text-white text-sm hover:bg-black disabled:opacity-60 disabled:cursor-not-allowed"
                        type="button"
                        onClick={handleConfirm}
                        disabled={loading}
                    >
                        {loading ? "Saving..." : "Confirm"}
                    </button>
                </div>
            </div>
        </div>
    );
}
