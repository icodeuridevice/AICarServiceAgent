import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchBookings } from "../api/bookings";
import type { Booking } from "../types/booking";
import LoadingSpinner from "../components/LoadingSpinner";
import ErrorBanner from "../components/ErrorBanner";
import EmptyState from "../components/EmptyState";

const getStatusClassName = (status: string): string => {
    switch (status) {
        case "CONFIRMED":
            return "bg-green-100 text-green-700";
        case "IN_PROGRESS":
            return "bg-yellow-100 text-yellow-700";
        case "COMPLETED":
            return "bg-blue-100 text-blue-700";
        case "CANCELLED":
            return "bg-red-100 text-red-700";
        default:
            return "bg-gray-100 text-gray-700";
    }
};

const getReminderStatus = (status: string): "Scheduled" | "Not Applicable" => {
    return status === "CONFIRMED" ? "Scheduled" : "Not Applicable";
};

const getReminderStatusClassName = (status: "Scheduled" | "Not Applicable"): string => {
    return status === "Scheduled" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-700";
};

const parseDateOnly = (value: string): Date | null => {
    const datePart = value.split("T")[0];
    const [yearRaw, monthRaw, dayRaw] = datePart.split("-");

    const year = Number(yearRaw);
    const month = Number(monthRaw);
    const day = Number(dayRaw);

    if (!Number.isInteger(year) || !Number.isInteger(month) || !Number.isInteger(day)) {
        return null;
    }

    const parsed = new Date(year, month - 1, day);

    if (Number.isNaN(parsed.getTime())) {
        return null;
    }

    if (parsed.getFullYear() !== year || parsed.getMonth() !== month - 1 || parsed.getDate() !== day) {
        return null;
    }

    return parsed;
};

const isWithinDateRange = (serviceDate: string, lowerBound: Date, upperBound: Date): boolean => {
    const parsedServiceDate = parseDateOnly(serviceDate);

    if (!parsedServiceDate) {
        return false;
    }

    return parsedServiceDate >= lowerBound && parsedServiceDate <= upperBound;
};

export default function Reminders() {
    const [bookings, setBookings] = useState<Booking[]>([]);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string>("");

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

    const upcomingBookings = useMemo(() => {
        const today = new Date();
        today.setHours(0, 0, 0, 0);

        const sevenDaysFromToday = new Date(today);
        sevenDaysFromToday.setDate(sevenDaysFromToday.getDate() + 7);

        return bookings.filter((booking) => isWithinDateRange(booking.service_date, today, sevenDaysFromToday));
    }, [bookings]);

    const handleSendReminder = (): void => {
        return;
    };

    if (loading) {
        return <LoadingSpinner />;
    }

    if (error) {
        return <ErrorBanner message={error} />;
    }

    if (upcomingBookings.length === 0) {
        return (
            <EmptyState
                title="No upcoming bookings"
                description="There are no bookings in the next 7 days."
            />
        );
    }

    return (
        <div className="bg-white border rounded-md overflow-hidden">
            <table className="w-full text-sm">
                <thead className="bg-gray-50 text-left text-gray-600">
                    <tr>
                        <th className="px-4 py-3 font-medium">Booking ID</th>
                        <th className="px-4 py-3 font-medium">Customer</th>
                        <th className="px-4 py-3 font-medium">Phone</th>
                        <th className="px-4 py-3 font-medium">Service Date</th>
                        <th className="px-4 py-3 font-medium">Status</th>
                        <th className="px-4 py-3 font-medium">Reminder Status</th>
                    </tr>
                </thead>
                <tbody>
                    {upcomingBookings.map((booking) => {
                        const reminderStatus = getReminderStatus(booking.status);
                        const isScheduled = reminderStatus === "Scheduled";

                        return (
                            <tr key={booking.id} className="border-t hover:bg-gray-50">
                                <td className="px-4 py-3 text-gray-700">{booking.id}</td>
                                <td className="px-4 py-3 text-gray-700">{booking.customer_name}</td>
                                <td className="px-4 py-3 text-gray-700">{booking.phone}</td>
                                <td className="px-4 py-3 text-gray-700">{booking.service_date}</td>
                                <td className="px-4 py-3">
                                    <span
                                        className={`inline-flex px-2 py-1 rounded text-xs font-medium ${getStatusClassName(booking.status)}`}
                                    >
                                        {booking.status}
                                    </span>
                                </td>
                                <td className="px-4 py-3">
                                    <div className="flex items-center gap-2">
                                        <span
                                            className={`inline-flex px-2 py-1 rounded text-xs font-medium ${getReminderStatusClassName(reminderStatus)}`}
                                        >
                                            {reminderStatus}
                                        </span>
                                        <button
                                            type="button"
                                            className="text-xs bg-gray-800 text-white px-3 py-1 rounded hover:bg-black disabled:opacity-50 disabled:cursor-not-allowed"
                                            disabled={!isScheduled}
                                            onClick={handleSendReminder}
                                        >
                                            Send Reminder
                                        </button>
                                    </div>
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
}
