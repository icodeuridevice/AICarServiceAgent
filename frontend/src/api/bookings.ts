import api from "./client";
import type { Booking } from "../types/booking";

interface FetchBookingsResponse {
    data: Booking[];
}

export const fetchBookings = async (): Promise<Booking[]> => {
    const response = await api.get<FetchBookingsResponse>("/bookings");
    return response.data.data;
};
