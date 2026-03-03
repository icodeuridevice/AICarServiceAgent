import { formatINR } from "../utils/format";

export default function Dashboard() {
    return (
        <div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">

                <div className="bg-white border rounded-md p-4">
                    <h2 className="text-sm font-medium text-gray-500 mb-1">Bookings Today</h2>
                    <p className="text-3xl font-bold text-gray-900">12</p>
                </div>

                <div className="bg-white border rounded-md p-4">
                    <h2 className="text-sm font-medium text-gray-500 mb-1">Active Jobs</h2>
                    <p className="text-3xl font-bold text-gray-900">4</p>
                </div>

                <div className="bg-white border rounded-md p-4">
                    <h2 className="text-sm font-medium text-gray-500 mb-1">Revenue Today</h2>
                    <p className="text-3xl font-bold text-gray-900">{formatINR(1240)}</p>
                </div>

            </div>
        </div>
    );
}
