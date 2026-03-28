import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchBookings } from "../api/bookings";
import {
    completeJobCard,
    createJobCard,
    fetchActiveJobCards,
    getJobCardApiErrorMessage,
    startJobCard,
} from "../api/jobcards";
import type { Booking } from "../types/booking";
import type { JobCard } from "../types/jobcard";
import { formatINR } from "../utils/format";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorBanner from "../components/ErrorBanner";
import EmptyState from "../components/EmptyState";
import StatusBadge from "../components/StatusBadge";
import Toast, { type ToastState } from "../components/Toast";

const isBookingLocked = (status: string): boolean => {
    return status === "COMPLETED" || status === "CANCELLED";
};

const formatDate = (value: string): string => {
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

const formatTime = (value?: string): string => {
    if (!value) {
        return "Time not set";
    }

    const parsedTime = new Date(`1970-01-01T${value.slice(0, 5)}:00`);

    if (Number.isNaN(parsedTime.getTime())) {
        return value;
    }

    return new Intl.DateTimeFormat("en-IN", {
        hour: "numeric",
        minute: "2-digit",
        hour12: true,
    }).format(parsedTime);
};

const formatDateTime = (value: string | null): string => {
    if (!value) {
        return "-";
    }

    const parsedDate = new Date(value);

    if (Number.isNaN(parsedDate.getTime())) {
        return value;
    }

    return parsedDate.toLocaleString("en-IN");
};

const primaryButtonClassName =
    "inline-flex items-center justify-center rounded-2xl bg-blue-600 px-3 py-2 text-xs font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60";
const secondaryButtonClassName =
    "inline-flex items-center justify-center rounded-2xl border border-blue-200 bg-blue-50 px-3 py-2 text-xs font-semibold text-blue-700 transition hover:bg-blue-100 disabled:cursor-not-allowed disabled:opacity-60";

export default function JobCards() {
    const [jobcards, setJobcards] = useState<JobCard[]>([]);
    const [bookings, setBookings] = useState<Booking[]>([]);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string>("");
    const [toast, setToast] = useState<ToastState | null>(null);
    const [creatingBookingId, setCreatingBookingId] = useState<number | null>(null);
    const [startingJobcardId, setStartingJobcardId] = useState<number | null>(null);
    const [completingJobcardId, setCompletingJobcardId] = useState<number | null>(null);

    const loadData = useCallback(async (showLoader = true): Promise<void> => {
        try {
            if (showLoader) {
                setLoading(true);
            }

            setError("");
            const [activeJobcards, allBookings] = await Promise.all([
                fetchActiveJobCards(),
                fetchBookings(),
            ]);
            setJobcards(activeJobcards);
            setBookings(allBookings);
        } catch (err: unknown) {
            setError(getJobCardApiErrorMessage(err, "Failed to fetch job cards."));
        } finally {
            if (showLoader) {
                setLoading(false);
            }
        }
    }, []);

    useEffect(() => {
        void loadData();
    }, [loadData]);

    const jobcardsByBookingId = useMemo(() => {
        return new Map<number, JobCard>(
            jobcards.map((jobcard) => [jobcard.booking_id, jobcard])
        );
    }, [jobcards]);

    const bookingsById = useMemo(() => {
        return new Map<number, Booking>(bookings.map((booking) => [booking.id, booking]));
    }, [bookings]);

    const readyBookings = useMemo(() => {
        return bookings.filter((booking) => !jobcardsByBookingId.has(booking.id));
    }, [bookings, jobcardsByBookingId]);

    const handleCreateJobCard = async (booking: Booking): Promise<void> => {
        if (isBookingLocked(booking.status) || jobcardsByBookingId.has(booking.id)) {
            return;
        }

        try {
            setCreatingBookingId(booking.id);
            await createJobCard(booking.id);
            await loadData(false);
            setToast({
                type: "success",
                message: "Booking updated",
            });
        } catch {
            setToast({
                type: "error",
                message: "Something went wrong",
            });
        } finally {
            setCreatingBookingId(null);
        }
    };

    const handleStartJobCard = async (jobcard: JobCard): Promise<void> => {
        const booking = bookingsById.get(jobcard.booking_id);

        if (booking && isBookingLocked(booking.status)) {
            return;
        }

        try {
            setStartingJobcardId(jobcard.id);
            await startJobCard(jobcard.id);
            await loadData(false);
            setToast({
                type: "success",
                message: "Booking updated",
            });
        } catch {
            setToast({
                type: "error",
                message: "Something went wrong",
            });
        } finally {
            setStartingJobcardId(null);
        }
    };

    const handleCompleteJobCard = async (jobcardId: number): Promise<void> => {
        try {
            setCompletingJobcardId(jobcardId);
            await completeJobCard(jobcardId);
            await loadData(false);
            setToast({
                type: "success",
                message: "Booking updated",
            });
        } catch {
            setToast({
                type: "error",
                message: "Something went wrong",
            });
        } finally {
            setCompletingJobcardId(null);
        }
    };

    if (loading) {
        return <LoadingSpinner />;
    }

    if (error) {
        return <ErrorBanner message={error} />;
    }

    return (
        <div className="space-y-6">
            {toast && <Toast toast={toast} onClose={() => setToast(null)} />}

            <section className="rounded-3xl border border-slate-200 bg-gradient-to-br from-white via-slate-50 to-blue-50 px-6 py-6 shadow-sm">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
                    <div className="max-w-2xl">
                        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-blue-600">
                            Workshop Flow
                        </p>
                        <h2 className="mt-3 text-2xl font-semibold text-slate-900">
                            Create and manage job cards from live bookings
                        </h2>
                        <p className="mt-2 text-sm leading-6 text-slate-600">
                            Create job cards from active bookings, then move workshop jobs through
                            their next actions from one simple screen.
                        </p>
                    </div>

                    <div className="grid gap-3 sm:grid-cols-2">
                        <div className="rounded-2xl border border-slate-200 bg-white/90 p-4 shadow-sm">
                            <p className="text-sm font-medium text-slate-500">Active job cards</p>
                            <p className="mt-2 text-3xl font-semibold text-slate-900">
                                {jobcards.length}
                            </p>
                        </div>
                        <div className="rounded-2xl border border-slate-200 bg-white/90 p-4 shadow-sm">
                            <p className="text-sm font-medium text-slate-500">Ready to create</p>
                            <p className="mt-2 text-3xl font-semibold text-slate-900">
                                {
                                    readyBookings.filter((booking) => !isBookingLocked(booking.status))
                                        .length
                                }
                            </p>
                        </div>
                    </div>
                </div>
            </section>

            <section className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
                <div className="border-b border-slate-200 px-6 py-5">
                    <h3 className="text-lg font-semibold text-slate-900">Create JobCard</h3>
                    <p className="mt-1 text-sm text-slate-500">
                        Use the bookings below to create a new job card. Completed and cancelled
                        bookings stay disabled.
                    </p>
                </div>

                {readyBookings.length === 0 ? (
                    <div className="px-6 py-10">
                        <EmptyState
                            title="No bookings available"
                            description="Every active booking already has a job card or is no longer actionable."
                        />
                    </div>
                ) : (
                    <div className="overflow-x-auto px-2 py-2">
                        <table className="min-w-[860px] w-full text-sm">
                            <thead className="text-left text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                                <tr>
                                    <th className="px-4 py-4">Booking</th>
                                    <th className="px-4 py-4">Service</th>
                                    <th className="px-4 py-4">Schedule</th>
                                    <th className="px-4 py-4">Status</th>
                                    <th className="px-4 py-4 text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                                {readyBookings.map((booking) => {
                                    const actionDisabled = isBookingLocked(booking.status);
                                    const isProcessing = creatingBookingId === booking.id;

                                    return (
                                        <tr key={booking.id} className="transition hover:bg-slate-50/80">
                                            <td className="px-4 py-5 align-top">
                                                <div className="space-y-1">
                                                    <p className="font-semibold text-slate-900">
                                                        #{String(booking.id).padStart(4, "0")}
                                                    </p>
                                                    <p className="text-sm text-slate-500">
                                                        {booking.customer_name !== "N/A"
                                                            ? booking.customer_name
                                                            : "Customer details pending"}
                                                    </p>
                                                </div>
                                            </td>
                                            <td className="px-4 py-5 align-top">
                                                <div className="space-y-1">
                                                    <p className="font-medium text-slate-900">
                                                        {booking.service_type}
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
                                                        {formatDate(booking.service_date)}
                                                    </p>
                                                    <p className="text-sm text-slate-500">
                                                        {formatTime(booking.service_time)}
                                                    </p>
                                                </div>
                                            </td>
                                            <td className="px-4 py-5 align-top">
                                                <StatusBadge status={booking.status} />
                                            </td>
                                            <td className="px-4 py-5 align-top">
                                                <div className="flex justify-end">
                                                    <button
                                                        className={primaryButtonClassName}
                                                        type="button"
                                                        disabled={actionDisabled || isProcessing}
                                                        onClick={() => void handleCreateJobCard(booking)}
                                                    >
                                                        {isProcessing
                                                            ? "Processing..."
                                                            : "Create JobCard"}
                                                    </button>
                                                </div>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                )}
            </section>

            <section className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
                <div className="border-b border-slate-200 px-6 py-5">
                    <h3 className="text-lg font-semibold text-slate-900">Active JobCards</h3>
                    <p className="mt-1 text-sm text-slate-500">
                        Start or complete active workshop jobs using the existing job card APIs.
                    </p>
                </div>

                {jobcards.length === 0 ? (
                    <div className="px-6 py-10">
                        <EmptyState
                            title="No active job cards found"
                            description="Create a job card from a booking to see it here."
                        />
                    </div>
                ) : (
                    <div className="overflow-x-auto px-2 py-2">
                        <table className="min-w-[920px] w-full text-sm">
                            <thead className="text-left text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                                <tr>
                                    <th className="px-4 py-4">JobCard</th>
                                    <th className="px-4 py-4">Booking</th>
                                    <th className="px-4 py-4">Technician</th>
                                    <th className="px-4 py-4">Status</th>
                                    <th className="px-4 py-4">Started</th>
                                    <th className="px-4 py-4">Cost</th>
                                    <th className="px-4 py-4 text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                                {jobcards.map((jobcard) => {
                                    const booking = bookingsById.get(jobcard.booking_id);
                                    const actionDisabled =
                                        jobcard.status === "COMPLETED" ||
                                        (booking ? isBookingLocked(booking.status) : false);
                                    const isStarting = startingJobcardId === jobcard.id;
                                    const isCompleting = completingJobcardId === jobcard.id;

                                    return (
                                        <tr key={jobcard.id} className="transition hover:bg-slate-50/80">
                                            <td className="px-4 py-5 align-top">
                                                <p className="font-semibold text-slate-900">
                                                    #{String(jobcard.id).padStart(4, "0")}
                                                </p>
                                            </td>
                                            <td className="px-4 py-5 align-top">
                                                <div className="space-y-1">
                                                    <p className="font-medium text-slate-900">
                                                        Booking #{jobcard.booking_id}
                                                    </p>
                                                    <p className="text-sm text-slate-500">
                                                        {booking?.service_type ?? "Service request"}
                                                    </p>
                                                </div>
                                            </td>
                                            <td className="px-4 py-5 align-top text-slate-700">
                                                {jobcard.technician_name ?? "-"}
                                            </td>
                                            <td className="px-4 py-5 align-top">
                                                <StatusBadge status={jobcard.status} />
                                            </td>
                                            <td className="px-4 py-5 align-top text-slate-700">
                                                {formatDateTime(jobcard.started_at)}
                                            </td>
                                            <td className="px-4 py-5 align-top text-slate-700">
                                                {jobcard.total_cost === null
                                                    ? "-"
                                                    : formatINR(jobcard.total_cost)}
                                            </td>
                                            <td className="px-4 py-5 align-top">
                                                <div className="flex justify-end gap-2">
                                                    <button
                                                        className={secondaryButtonClassName}
                                                        type="button"
                                                        disabled={actionDisabled || isStarting || isCompleting}
                                                        onClick={() => void handleStartJobCard(jobcard)}
                                                    >
                                                        {isStarting ? "Processing..." : "Start Job"}
                                                    </button>
                                                    <button
                                                        className={primaryButtonClassName}
                                                        type="button"
                                                        disabled={actionDisabled || isStarting || isCompleting}
                                                        onClick={() => void handleCompleteJobCard(jobcard.id)}
                                                    >
                                                        {isCompleting ? "Processing..." : "Complete Job"}
                                                    </button>
                                                </div>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                )}
            </section>
        </div>
    );
}
