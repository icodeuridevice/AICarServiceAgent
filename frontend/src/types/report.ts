export interface DailyReport {
    date: string;
    total_bookings: number;
    in_progress_jobs: number;
    completed_jobs: number;
    cancelled_bookings: number;
    total_revenue: number;
}
