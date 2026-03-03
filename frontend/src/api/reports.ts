import api from "./client";
import type { DailyReport } from "../types/report";

interface FetchDailyReportResponse {
    data: DailyReport;
}

export const fetchDailyReport = async (): Promise<DailyReport> => {
    const response = await api.get<FetchDailyReportResponse>("/reports/daily");
    return response.data.data;
};
