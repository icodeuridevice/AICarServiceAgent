import { useEffect, useState } from "react";
import { fetchDailyReport } from "../api/reports";
import type { DailyReport } from "../types/report";
import { formatINR } from "../utils/format";
import ErrorBanner from "../components/ErrorBanner";

export default function Dashboard() {
    const [report, setReport] = useState<DailyReport | null>(null);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string>("");

    useEffect(() => {
        let isMounted = true;

        const loadReport = async (): Promise<void> => {
            try {
                setLoading(true);
                setError("");
                const data = await fetchDailyReport();
                if (isMounted) {
                    setReport(data);
                }
            } catch (err: unknown) {
                if (isMounted) {
                    if (err instanceof Error && err.message) {
                        setError(err.message);
                    } else {
                        setError("Failed to fetch daily report.");
                    }
                }
            } finally {
                if (isMounted) {
                    setLoading(false);
                }
            }
        };

        void loadReport();

        return () => {
            isMounted = false;
        };
    }, []);

    if (loading) {
        return (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                {Array.from({ length: 4 }).map((_, index) => (
                    <div key={index} className="bg-white rounded-md border p-6 animate-pulse">
                        <div className="h-4 w-28 rounded bg-gray-200" />
                        <div className="mt-4 h-8 w-16 rounded bg-gray-200" />
                    </div>
                ))}
            </div>
        );
    }

    if (error) {
        return <ErrorBanner message={error} />;
    }

    if (!report) {
        return <p className="text-gray-600">No report data found.</p>;
    }

    return (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <div className="bg-white rounded-md border p-6">
                <h2 className="text-sm text-gray-500">Total Bookings</h2>
                <p className="text-2xl font-semibold text-gray-900">{report.total_bookings}</p>
                <p className="mt-2 text-xs text-gray-500">Cancelled: {report.cancelled_bookings}</p>
            </div>

            <div className="bg-white rounded-md border p-6">
                <h2 className="text-sm text-gray-500">In Progress Jobs</h2>
                <p className="text-2xl font-semibold text-gray-900">{report.in_progress_jobs}</p>
            </div>

            <div className="bg-white rounded-md border p-6">
                <h2 className="text-sm text-gray-500">Completed Jobs</h2>
                <p className="text-2xl font-semibold text-gray-900">{report.completed_jobs}</p>
            </div>

            <div className="bg-white rounded-md border p-6">
                <h2 className="text-sm text-gray-500">Revenue Today (₹)</h2>
                <p className="text-2xl font-semibold text-gray-900">{formatINR(report.total_revenue)}</p>
            </div>
        </div>
    );
}
