export interface JobCard {
    id: number;
    booking_id: number;
    technician_name: string | null;
    status: string;
    total_cost: number | null;
    completed_at: string | null;
}
