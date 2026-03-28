import axios from "axios";
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

export const getBookingApiErrorMessage = (
    err: unknown,
    fallbackMessage: string
): string => {
    if (!axios.isAxiosError(err)) {
        if (err instanceof Error && err.message) {
            return err.message;
        }
        return fallbackMessage;
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

    return fallbackMessage;
};

export const rescheduleBooking = async (
    bookingId: number,
    newDate: string,
    newTime: string
): Promise<void> => {
    await api.put("/bookings/reschedule", {
        booking_id: bookingId,
        new_date: newDate,
        new_time: newTime,
    });
};

export const cancelBooking = async (bookingId: number): Promise<void> => {
    await api.patch(`/bookings/${bookingId}/cancel`);
};
