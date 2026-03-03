import api from "./client";
import axios from "axios";
import type { JobCard } from "../types/jobcard";

interface FetchActiveJobCardsResponse {
    data: RawJobCard[];
}

interface RawJobCard {
    id?: number;
    booking_id?: number;
    technician_name?: string | null;
    status?: string;
    total_cost?: number | null;
    completed_at?: string | null;
}

const normalizeJobCard = (raw: RawJobCard): JobCard => {
    if (raw.id === undefined) {
        throw new Error("Job card response is missing job card id.");
    }

    if (raw.booking_id === undefined) {
        throw new Error("Job card response is missing booking id.");
    }

    return {
        id: raw.id,
        booking_id: raw.booking_id,
        technician_name: raw.technician_name ?? null,
        status: raw.status ?? "IN_PROGRESS",
        total_cost: raw.total_cost ?? null,
        completed_at: raw.completed_at ?? null,
    };
};

export const fetchActiveJobCards = async (): Promise<JobCard[]> => {
    const response = await api.get<FetchActiveJobCardsResponse>("/jobcards/active");
    return response.data.data.map(normalizeJobCard);
};

export const createJobCard = async (
    bookingId: number,
    technicianName: string
): Promise<void> => {
    await api.post("/jobcards/", null, {
        params: {
            booking_id: bookingId,
            technician_name: technicianName,
        },
    });
};

export const completeJobCard = async (jobcardId: number): Promise<void> => {
    await api.post(`/jobcards/${jobcardId}/complete`);
};

export const hasJobCardForBooking = async (bookingId: number): Promise<boolean> => {
    try {
        await api.get(`/jobcards/booking/${bookingId}`);
        return true;
    } catch (err: unknown) {
        if (axios.isAxiosError(err) && err.response?.status === 404) {
            return false;
        }
        throw err;
    }
};
