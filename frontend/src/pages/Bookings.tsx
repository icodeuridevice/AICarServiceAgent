import { useCallback, useEffect, useState } from "react";
import {
    cancelBooking,
    fetchBookings,
    getBookingApiErrorMessage,
} from "../api/bookings";
import type { Booking } from "../types/booking";
import RescheduleModal from "../components/RescheduleModal";
import ErrorBanner from "../components/ErrorBanner";
import StatusBadge from "../components/StatusBadge";

const canManageBooking = (status: string): boolean => {
    return status === "PENDING" || status === "CONFIRMED";
};

const formatServiceDate = (value: string): string => {
    const parsedDate = new Date(`${value}T00:00:00`);

    if (Number.isNaN(parsedDate.getTime())) {
        return value;
    }

    return new Intl.DateTimeFormat("en-IN", {
        day: "numeric",
        month: "short",
        year: "numeric",
    }).format(parsedDate);
};

const formatServiceTime = (value?: string): string => {
    if (!value) {
        return "Time not set";
    }

    const normalizedValue = value.slice(0, 5);
    const parsedTime = new Date(`1970-01-01T${normalizedValue}:00`);

    if (Number.isNaN(parsedTime.getTime())) {
        return normalizedValue;
    }

    return new Intl.DateTimeFormat("en-IN", {
        hour: "numeric",
        minute: "2-digit",
        hour12: true,
    }).format(parsedTime);
};

export default function Bookings() {
    const [bookings, setBookings] = useState<Booking[]>([]);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string>("");
    const [operationError, setOperationError] = useState<string>("");
    const [selectedBookingForReschedule, setSelectedBookingForReschedule] = useState<Booking | null>(null);
    const [showModal, setShowModal] = useState<boolean>(false);
    const [cancellingBookingId, setCancellingBookingId] = useState<number | null>(null);

    const loadBookings = useCallback(async (): Promise<void> => {
        try {
            setLoading(true);
            setError("");
            const data = await fetchBookings();
            setBookings(data);
        } catch (err: unknown) {
            if (err instanceof Error && err.message) {
                setError(err.message);
            } else {
                setError("Failed to fetch bookings.");
            }
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        void loadBookings();
    }, [loadBookings]);

    const handleOpenReschedule = (booking: Booking): void => {
        setOperationError("");
        setSelectedBookingForReschedule(booking);
        setShowModal(true);
    };

    const handleCloseReschedule = (): void => {
        setShowModal(false);
        setSelectedBookingForReschedule(null);
    };

    const handleCancelBooking = async (booking: Booking): Promise<void> => {
        if (!canManageBooking(booking.status)) {
            return;
        }

        const confirmed = window.confirm(
            `Cancel booking #${booking.id} scheduled for ${booking.service_date}?`
        );

        if (!confirmed) {
            return;
        }

        try {
            setCancellingBookingId(booking.id);
            setOperationError("");
            await cancelBooking(booking.id);
            await loadBookings();
        } catch (err: unknown) {
            setOperationError(getBookingApiErrorMessage(err, "Failed to cancel booking."));
        } finally {
            setCancellingBookingId(null);
        }
    };

    if (loading) {
        return (
            <div className="rounded-3xl border border-slate-200 bg-white px-6 py-12 shadow-sm">
                <div className="flex items-center justify-center gap-3 text-sm font-medium text-slate-600">
                    <div className="h-5 w-5 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
                    <span>Loading bookings...</span>
                </div>
            </div>
        );
    }

    if (error) {
        return <ErrorBanner message={error} />;
    }

    return (
        <div className="space-y-6">
            <section className="rounded-3xl border border-slate-200 bg-gradient-to-br from-white via-slate-50 to-blue-50 px-6 py-6 shadow-sm">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
                    <div className="max-w-2xl">
                        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-blue-600">
                            Service Desk
                        </p>
                        <h2 className="mt-3 text-2xl font-semibold text-slate-900">
                            Manage every booking from one clean queue
                        </h2>
                        <p className="mt-2 text-sm leading-6 text-slate-600">
                            Review upcoming appointments, reschedule service dates, and cancel
                            requests without leaving the dashboard.
                        </p>
                    </div>

                    <div className="w-full max-w-xs rounded-2xl border border-slate-200 bg-white/80 p-4 shadow-sm backdrop-blur">
                        <p className="text-sm font-medium text-slate-500">Total bookings</p>
                        <p className="mt-2 text-3xl font-semibold text-slate-900">
                            {bookings.length}
                        </p>
                        <p className="mt-1 text-sm text-slate-500">
                            Live list of service requests and appointment changes
                        </p>
                    </div>
                </div>
            </section>

            <section className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
                <div className="flex flex-col gap-4 border-b border-slate-200 px-6 py-5 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                        <h3 className="text-lg font-semibold text-slate-900">Bookings table</h3>
                        <p className="mt-1 text-sm text-slate-500">
                            Use the actions column to adjust schedules or cancel eligible bookings.
                        </p>
                    </div>
                    <div className="inline-flex rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-slate-600">
                        {bookings.length} records
                    </div>
                </div>

                {operationError && (
                    <div className="px-6 pt-6">
                        <ErrorBanner message={operationError} />
                    </div>
                )}

                {bookings.length === 0 ? (
                    <div className="px-6 py-16 text-center">
                        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-500">
                            0
                        </div>
                        <h3 className="mt-4 text-lg font-semibold text-slate-900">
                            No bookings found
                        </h3>
                        <p className="mt-2 text-sm text-slate-500">
                            New service requests will appear here as soon as customers book.
                        </p>
                    </div>
                ) : (
                    <div className="overflow-x-auto px-2 py-2">
                        <table className="min-w-[920px] w-full text-sm">
                            <thead className="text-left text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                                <tr>
                                    <th className="px-4 py-4">Booking</th>
                                    <th className="px-4 py-4">Customer</th>
                                    <th className="px-4 py-4">Service</th>
                                    <th className="px-4 py-4">Schedule</th>
                                    <th className="px-4 py-4">Status</th>
                                    <th className="px-4 py-4 text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                                {bookings.map((booking) => (
                                    <tr key={booking.id} className="transition hover:bg-slate-50/80">
                                        <td className="px-4 py-5 align-top">
                                            <div className="space-y-1">
                                                <p className="font-semibold text-slate-900">
                                                    #{String(booking.id).padStart(4, "0")}
                                                </p>
                                                <p className="text-sm text-slate-500">
                                                    {booking.vehicle_number !== "-"
                                                        ? booking.vehicle_number
                                                        : "Vehicle not shared"}
                                                </p>
                                            </div>
                                        </td>
                                        <td className="px-4 py-5 align-top">
                                            <div className="space-y-1">
                                                <p className="font-medium text-slate-900">
                                                    {booking.customer_name !== "N/A"
                                                        ? booking.customer_name
                                                        : "Customer details pending"}
                                                </p>
                                                <p className="text-sm text-slate-500">
                                                    {booking.phone !== "N/A"
                                                        ? booking.phone
                                                        : "Phone not available"}
                                                </p>
                                            </div>
                                        </td>
                                        <td className="px-4 py-5 align-top">
                                            <div className="space-y-1">
                                                <p className="font-medium text-slate-900">
                                                    {booking.service_type}
                                                </p>
                                                <p className="text-sm text-slate-500">
                                                    Service request
                                                </p>
                                            </div>
                                        </td>
                                        <td className="px-4 py-5 align-top">
                                            <div className="space-y-1">
                                                <p className="font-medium text-slate-900">
                                                    {formatServiceDate(booking.service_date)}
                                                </p>
                                                <p className="text-sm text-slate-500">
                                                    {formatServiceTime(booking.service_time)}
                                                </p>
                                            </div>
                                        </td>
                                        <td className="px-4 py-5 align-top">
                                            <StatusBadge status={booking.status} />
                                        </td>
                                        <td className="px-4 py-5 align-top">
                                            <div className="flex justify-end gap-2">
                                                <button
                                                    className="inline-flex items-center justify-center rounded-2xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 shadow-sm transition hover:border-slate-300 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                                                    type="button"
                                                    disabled={!canManageBooking(booking.status)}
                                                    title={
                                                        canManageBooking(booking.status)
                                                            ? "Reschedule booking"
                                                            : "Only PENDING or CONFIRMED bookings can be rescheduled"
                                                    }
                                                    onClick={() => handleOpenReschedule(booking)}
                                                >
                                                    Reschedule
                                                </button>
                                                <button
                                                    className="inline-flex items-center justify-center rounded-2xl border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold text-red-700 transition hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50"
                                                    type="button"
                                                    disabled={
                                                        !canManageBooking(booking.status) ||
                                                        cancellingBookingId === booking.id
                                                    }
                                                    title={
                                                        canManageBooking(booking.status)
                                                            ? "Cancel booking"
                                                            : "Only PENDING or CONFIRMED bookings can be cancelled"
                                                    }
                                                    onClick={() => void handleCancelBooking(booking)}
                                                >
                                                    {cancellingBookingId === booking.id
                                                        ? "Cancelling..."
                                                        : "Cancel"}
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </section>

            {showModal && selectedBookingForReschedule && (
                <RescheduleModal
                    bookingId={selectedBookingForReschedule.id}
                    currentDate={selectedBookingForReschedule.service_date}
                    currentTime={selectedBookingForReschedule.service_time}
                    onClose={handleCloseReschedule}
                    onSuccess={loadBookings}
                />
            )}
        </div>
    );
}
