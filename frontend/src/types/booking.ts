export interface Booking {
    id: number;
    customer_name: string;
    phone: string;
    vehicle_number: string;
    service_type: string;
    service_date: string;
    service_time?: string;
    status: string;
}
