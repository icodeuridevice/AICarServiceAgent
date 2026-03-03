import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { fetchBookings } from "../api/bookings";
import {
    completeJobCard,
    createJobCard,
    fetchActiveJobCards,
    hasJobCardForBooking,
} from "../api/jobcards";
import type { Booking } from "../types/booking";
import type { JobCard } from "../types/jobcard";
import { formatINR } from "../utils/format";

const getStatusClassName = (status: string): string => {
    switch (status) {
        case "IN_PROGRESS":
            return "bg-yellow-100 text-yellow-700";
        case "COMPLETED":
            return "bg-blue-100 text-blue-700";
        default:
            return "bg-gray-100 text-gray-700";
    }
};

const formatCompletedAt = (completedAt: string | null): string => {
    if (!completedAt) {
        return "-";
    }

    const parsedDate = new Date(completedAt);
    if (Number.isNaN(parsedDate.getTime())) {
        return completedAt;
    }

    return parsedDate.toLocaleString();
};

const getApiErrorMessage = (err: unknown, fallbackMessage: string): string => {
    if (!axios.isAxiosError(err)) {
        if (err instanceof Error && err.message) {
            return err.message;
        }
        return fallbackMessage;
    }

    const detail = err.response?.data?.detail as unknown;
    if (typeof detail === "string" && detail.trim()) {
        return detail;
    }

    if (typeof err.message === "string" && err.message.trim()) {
        return err.message;
    }

    return fallbackMessage;
};

export default function JobCards() {
    const [jobcards, setJobcards] = useState<JobCard[]>([]);
    const [bookings, setBookings] = useState<Booking[]>([]);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string>("");
    const [operationError, setOperationError] = useState<string>("");

    const [showCreateModal, setShowCreateModal] = useState<boolean>(false);
    const [createBookingId, setCreateBookingId] = useState<string>("");
    const [createTechnicianName, setCreateTechnicianName] = useState<string>("");
    const [createLoading, setCreateLoading] = useState<boolean>(false);
    const [completingJobcardId, setCompletingJobcardId] = useState<number | null>(null);

    const loadData = useCallback(async (): Promise<void> => {
        try {
            setLoading(true);
            setError("");
            const [activeJobcards, allBookings] = await Promise.all([
                fetchActiveJobCards(),
                fetchBookings(),
            ]);
            setJobcards(activeJobcards);
            setBookings(allBookings);
        } catch (err: unknown) {
            setError(getApiErrorMessage(err, "Failed to fetch job cards."));
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        void loadData();
    }, [loadData]);

    const eligibleBookings = useMemo(() => {
        const bookingIdsWithActiveJobcards = new Set(
            jobcards.map((jobcard) => jobcard.booking_id)
        );

        return bookings.filter((booking) => {
            if (booking.status === "CANCELLED" || booking.status === "COMPLETED") {
                return false;
            }

            return !bookingIdsWithActiveJobcards.has(booking.id);
        });
    }, [bookings, jobcards]);

    const eligibleBookingIds = useMemo(() => {
        return new Set<number>(eligibleBookings.map((booking) => booking.id));
    }, [eligibleBookings]);

    const openCreateModal = (): void => {
        if (eligibleBookings.length === 0) {
            setOperationError("No eligible bookings available for creating a job card.");
            return;
        }

        setOperationError("");
        setCreateBookingId(String(eligibleBookings[0].id));
        setCreateTechnicianName("");
        setShowCreateModal(true);
    };

    const closeCreateModal = (): void => {
        setShowCreateModal(false);
        setCreateBookingId("");
        setCreateTechnicianName("");
    };

    const handleCreateJobCard = async (): Promise<void> => {
        const parsedBookingId = Number(createBookingId);
        const trimmedTechnicianName = createTechnicianName.trim();

        if (!Number.isInteger(parsedBookingId) || parsedBookingId <= 0) {
            setOperationError("Please enter a valid booking ID.");
            return;
        }

        if (!eligibleBookingIds.has(parsedBookingId)) {
            setOperationError("This booking already has a job card or cannot be used.");
            return;
        }

        if (!trimmedTechnicianName) {
            setOperationError("Technician name is required.");
            return;
        }

        try {
            setCreateLoading(true);
            setOperationError("");

            const jobcardAlreadyExists = await hasJobCardForBooking(parsedBookingId);
            if (jobcardAlreadyExists) {
                setOperationError("A job card already exists for this booking.");
                return;
            }

            await createJobCard(parsedBookingId, trimmedTechnicianName);
            closeCreateModal();
            await loadData();
        } catch (err: unknown) {
            setOperationError(getApiErrorMessage(err, "Failed to create job card."));
        } finally {
            setCreateLoading(false);
        }
    };

    const handleCompleteJobCard = async (jobcardId: number): Promise<void> => {
        try {
            setCompletingJobcardId(jobcardId);
            setOperationError("");
            await completeJobCard(jobcardId);
            await loadData();
        } catch (err: unknown) {
            setOperationError(getApiErrorMessage(err, "Failed to complete job card."));
        } finally {
            setCompletingJobcardId(null);
        }
    };

    if (loading) {
        return <p>Loading...</p>;
    }

    if (error) {
        return <p className="text-red-600">{error}</p>;
    }

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <p className="text-sm text-gray-600">Manage active workshop job cards.</p>
                <button
                    className="text-sm bg-gray-800 text-white px-3 py-2 rounded hover:bg-black disabled:opacity-50 disabled:cursor-not-allowed"
                    type="button"
                    onClick={openCreateModal}
                    disabled={eligibleBookings.length === 0}
                    title={
                        eligibleBookings.length === 0
                            ? "No eligible bookings available"
                            : "Create a new job card"
                    }
                >
                    Create JobCard
                </button>
            </div>

            {operationError && (
                <p className="text-sm text-red-600">{operationError}</p>
            )}

            <div className="bg-white border rounded-md overflow-hidden">
                <table className="w-full text-sm">
                    <thead className="bg-gray-50 text-left text-gray-600">
                        <tr>
                            <th className="px-4 py-3 font-medium">ID</th>
                            <th className="px-4 py-3 font-medium">Booking ID</th>
                            <th className="px-4 py-3 font-medium">Technician</th>
                            <th className="px-4 py-3 font-medium">Status</th>
                            <th className="px-4 py-3 font-medium">Cost</th>
                            <th className="px-4 py-3 font-medium">Completed</th>
                            <th className="px-4 py-3 font-medium">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {jobcards.map((jobcard) => (
                            <tr key={jobcard.id} className="border-t hover:bg-gray-50">
                                <td className="px-4 py-3 text-gray-700">{jobcard.id}</td>
                                <td className="px-4 py-3 text-gray-700">{jobcard.booking_id}</td>
                                <td className="px-4 py-3 text-gray-700">
                                    {jobcard.technician_name ?? "-"}
                                </td>
                                <td className="px-4 py-3">
                                    <span
                                        className={`inline-flex px-2 py-1 rounded text-xs font-medium ${getStatusClassName(jobcard.status)}`}
                                    >
                                        {jobcard.status}
                                    </span>
                                </td>
                                <td className="px-4 py-3 text-gray-700">
                                    {jobcard.total_cost === null ? "-" : formatINR(jobcard.total_cost)}
                                </td>
                                <td className="px-4 py-3 text-gray-700">
                                    {formatCompletedAt(jobcard.completed_at)}
                                </td>
                                <td className="px-4 py-3">
                                    {jobcard.status !== "COMPLETED" ? (
                                        <button
                                            className="text-xs bg-gray-800 text-white px-3 py-1 rounded hover:bg-black disabled:opacity-50 disabled:cursor-not-allowed"
                                            type="button"
                                            onClick={() => void handleCompleteJobCard(jobcard.id)}
                                            disabled={completingJobcardId === jobcard.id}
                                        >
                                            {completingJobcardId === jobcard.id ? "Completing..." : "Complete"}
                                        </button>
                                    ) : (
                                        <span className="text-xs text-gray-500">-</span>
                                    )}
                                </td>
                            </tr>
                        ))}
                        {jobcards.length === 0 && (
                            <tr className="border-t">
                                <td className="px-4 py-3 text-gray-500" colSpan={7}>
                                    No active job cards found.
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>

            {showCreateModal && (
                <div className="fixed inset-0 bg-black bg-opacity-40 flex items-center justify-center">
                    <div className="bg-white rounded-md p-6 w-96">
                        <h2 className="text-lg font-semibold text-gray-900">Create JobCard</h2>
                        <div className="mt-4">
                            <label className="block text-sm text-gray-700 mb-2" htmlFor="jobcard-booking-id">
                                Booking ID
                            </label>
                            <input
                                id="jobcard-booking-id"
                                className="w-full border rounded px-3 py-2 text-sm"
                                type="number"
                                min={1}
                                value={createBookingId}
                                onChange={(event) => setCreateBookingId(event.target.value)}
                            />
                            <p className="text-xs text-gray-500 mt-2">
                                Available IDs:{" "}
                                {eligibleBookings.map((booking) => booking.id).join(", ") || "None"}
                            </p>
                        </div>
                        <div className="mt-4">
                            <label className="block text-sm text-gray-700 mb-2" htmlFor="jobcard-technician-name">
                                Technician Name
                            </label>
                            <input
                                id="jobcard-technician-name"
                                className="w-full border rounded px-3 py-2 text-sm"
                                type="text"
                                value={createTechnicianName}
                                onChange={(event) => setCreateTechnicianName(event.target.value)}
                                placeholder="Enter technician name"
                            />
                        </div>
                        {operationError && <p className="text-xs text-red-600 mt-2">{operationError}</p>}
                        <div className="mt-5 flex justify-end gap-2">
                            <button
                                className="px-3 py-1 rounded border text-sm text-gray-700 hover:bg-gray-100"
                                type="button"
                                onClick={closeCreateModal}
                                disabled={createLoading}
                            >
                                Cancel
                            </button>
                            <button
                                className="px-3 py-1 rounded bg-gray-800 text-white text-sm hover:bg-black disabled:opacity-60 disabled:cursor-not-allowed"
                                type="button"
                                onClick={() => void handleCreateJobCard()}
                                disabled={createLoading}
                            >
                                {createLoading ? "Creating..." : "Create"}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
