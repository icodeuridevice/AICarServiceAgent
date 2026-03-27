import { useEffect, useState } from "react";
import { getBookingApiErrorMessage, rescheduleBooking } from "../api/bookings";
import ErrorBanner from "./ErrorBanner";

interface RescheduleModalProps {
    bookingId: number;
    currentDate: string;
    currentTime?: string;
    onClose: () => void;
    onSuccess: () => Promise<void> | void;
}

const toInputDate = (date: string): string => {
    return date.slice(0, 10);
};

const toInputTime = (time?: string): string => {
    if (!time) {
        return "";
    }

    return time.slice(0, 5);
};

const DATE_ONLY_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

export default function RescheduleModal({
    bookingId,
    currentDate,
    currentTime,
    onClose,
    onSuccess,
}: RescheduleModalProps) {
    const [newDate, setNewDate] = useState<string>(toInputDate(currentDate));
    const [loading, setLoading] = useState<boolean>(false);
    const [error, setError] = useState<string>("");
    const currentTimeValue = toInputTime(currentTime);

    useEffect(() => {
        const handleEscape = (event: KeyboardEvent) => {
            if (event.key === "Escape" && !loading) {
                onClose();
            }
        };

        const previousOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        window.addEventListener("keydown", handleEscape);

        return () => {
            document.body.style.overflow = previousOverflow;
            window.removeEventListener("keydown", handleEscape);
        };
    }, [loading, onClose]);

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
            await rescheduleBooking(Number(bookingId), newDate);
            onClose();
            void Promise.resolve(onSuccess());
        } catch (err: unknown) {
            setError(getBookingApiErrorMessage(err, "Failed to reschedule booking."));
        } finally {
            setLoading(false);
        }
    };

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 px-4 py-6 backdrop-blur-sm"
            role="presentation"
            onClick={(event) => {
                if (event.target === event.currentTarget && !loading) {
                    onClose();
                }
            }}
        >
            <div
                className="w-full max-w-lg rounded-3xl border border-slate-200 bg-white shadow-2xl"
                role="dialog"
                aria-modal="true"
                aria-labelledby="reschedule-title"
                onClick={(event) => event.stopPropagation()}
            >
                <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-6 py-5">
                    <div>
                        <p className="text-sm font-medium text-blue-600">Booking #{bookingId}</p>
                        <h2 id="reschedule-title" className="mt-1 text-xl font-semibold text-slate-900">
                            Reschedule booking
                        </h2>
                        <p className="mt-2 text-sm text-slate-500">
                            Pick a new service date. The current API keeps the existing time slot.
                        </p>
                    </div>
                    <button
                        className="rounded-full border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                        type="button"
                        onClick={onClose}
                        disabled={loading}
                    >
                        Close
                    </button>
                </div>

                <div className="space-y-5 px-6 py-6">
                    <div className="grid gap-4 sm:grid-cols-2">
                        <div>
                            <label
                                className="mb-2 block text-sm font-medium text-slate-700"
                                htmlFor="reschedule-date"
                            >
                                New date
                            </label>
                            <input
                                id="reschedule-date"
                                className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 shadow-sm outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                                type="date"
                                value={newDate}
                                onChange={(event) => setNewDate(event.target.value)}
                            />
                        </div>

                        <div>
                            <label
                                className="mb-2 block text-sm font-medium text-slate-700"
                                htmlFor="reschedule-time"
                            >
                                Time
                            </label>
                            <input
                                id="reschedule-time"
                                className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600 shadow-sm outline-none"
                                type="time"
                                value={currentTimeValue}
                                readOnly
                            />
                        </div>
                    </div>

                    <div className="rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-700">
                        {currentTimeValue
                            ? "Time changes are locked right now because the current reschedule API preserves the existing booking time."
                            : "This booking does not currently expose a service time, so only the date will be updated."}
                    </div>

                    {error && (
                        <div>
                            <ErrorBanner message={error} />
                        </div>
                    )}
                </div>

                <div className="flex justify-end gap-3 border-t border-slate-200 px-6 py-5">
                    <button
                        className="rounded-2xl border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                        type="button"
                        onClick={onClose}
                        disabled={loading}
                    >
                        Cancel
                    </button>
                    <button
                        className="rounded-2xl bg-slate-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                        type="button"
                        onClick={handleConfirm}
                        disabled={loading}
                    >
                        {loading ? "Saving..." : "Save changes"}
                    </button>
                </div>
            </div>
        </div>
    );
}
