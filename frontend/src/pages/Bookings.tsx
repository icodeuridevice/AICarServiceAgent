import { useEffect, useState } from "react";
import { fetchBookings } from "../api/bookings";
import type { Booking } from "../types/booking";

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

export default function Bookings() {
    const [bookings, setBookings] = useState<Booking[]>([]);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string>("");

    useEffect(() => {
        let isMounted = true;

        const loadBookings = async () => {
            try {
                setLoading(true);
                setError("");
                const data = await fetchBookings();

                if (isMounted) {
                    setBookings(data);
                }
            } catch (err: unknown) {
                if (!isMounted) {
                    return;
                }

                if (err instanceof Error && err.message) {
                    setError(err.message);
                } else {
                    setError("Failed to fetch bookings.");
                }
            } finally {
                if (isMounted) {
                    setLoading(false);
                }
            }
        };

        void loadBookings();

        return () => {
            isMounted = false;
        };
    }, []);

    if (loading) {
        return <p>Loading...</p>;
    }

    if (error) {
        return <p className="text-red-600">{error}</p>;
    }

    return (
        <div className="bg-white border rounded-md overflow-hidden">
            <table className="w-full text-sm">
                <thead className="bg-gray-50 text-left text-gray-600">
                    <tr>
                        <th className="px-4 py-3 font-medium">ID</th>
                        <th className="px-4 py-3 font-medium">Customer</th>
                        <th className="px-4 py-3 font-medium">Phone</th>
                        <th className="px-4 py-3 font-medium">Vehicle</th>
                        <th className="px-4 py-3 font-medium">Service</th>
                        <th className="px-4 py-3 font-medium">Date</th>
                        <th className="px-4 py-3 font-medium">Status</th>
                    </tr>
                </thead>
                <tbody>
                    {bookings.map((booking) => (
                        <tr key={booking.id} className="border-t hover:bg-gray-50">
                            <td className="px-4 py-3 text-gray-700">{booking.id}</td>
                            <td className="px-4 py-3 text-gray-700">{booking.customer_name}</td>
                            <td className="px-4 py-3 text-gray-700">{booking.phone}</td>
                            <td className="px-4 py-3 text-gray-700">{booking.vehicle_number}</td>
                            <td className="px-4 py-3 text-gray-700">{booking.service_type}</td>
                            <td className="px-4 py-3 text-gray-700">{booking.service_date}</td>
                            <td className="px-4 py-3">
                                <span
                                    className={`inline-flex px-2 py-1 rounded text-xs font-medium ${getStatusClassName(booking.status)}`}
                                >
                                    {booking.status}
                                </span>
                            </td>
                        </tr>
                    ))}
                    {bookings.length === 0 && (
                        <tr className="border-t">
                            <td className="px-4 py-3 text-gray-500" colSpan={7}>
                                No bookings found.
                            </td>
                        </tr>
                    )}
                </tbody>
            </table>
        </div>
    );
}
