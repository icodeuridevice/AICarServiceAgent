import api from "./client";
import type { Booking } from "../types/booking";

interface FetchBookingsResponse {
    data: RawBooking[];
}

interface RawBooking {
    id?: number;
    booking_id?: number;
    customer_name?: string;
    customer_phone?: string;
    phone?: string;
    vehicle_number?: string;
    service_type: string;
    service_date: string;
    service_time?: string;
    status: string;
}

const normalizeBooking = (raw: RawBooking): Booking => {
    const resolvedId = raw.id ?? raw.booking_id;

    if (resolvedId === undefined) {
        throw new Error("Booking response is missing booking id.");
    }

    return {
        id: resolvedId,
        customer_name: raw.customer_name ?? "N/A",
        phone: raw.phone ?? raw.customer_phone ?? "N/A",
        vehicle_number: raw.vehicle_number ?? "-",
        service_type: raw.service_type,
        service_date: raw.service_date,
        service_time: raw.service_time,
        status: raw.status,
    };
};

export const fetchBookings = async (): Promise<Booking[]> => {
    const response = await api.get<FetchBookingsResponse>("/bookings");
    return response.data.data.map(normalizeBooking);
};

export const rescheduleBooking = async (
    bookingId: number,
    newDate: string
): Promise<void> => {
    await api.put("/bookings/reschedule", {
        booking_id: bookingId,
        service_date: newDate,
    });
};
