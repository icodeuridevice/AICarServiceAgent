import React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { clearToken } from "../auth/auth";

interface DashboardLayoutProps {
    children: React.ReactNode;
    title: string;
}

export default function DashboardLayout({ children, title }: DashboardLayoutProps) {
    const navigate = useNavigate();

    const handleLogout = () => {
        clearToken();
        navigate("/login");
    };

    return (
        <div className="flex min-h-screen bg-gray-100">
            {/* Sidebar */}
            <aside className="w-64 bg-white border-r flex flex-col">
                <div className="h-16 flex items-center px-6 border-b">
                    <span className="font-bold text-lg text-gray-800">Garage Agent</span>
                </div>

                <nav className="flex-1 py-4 flex flex-col">
                    <NavLink
                        end
                        to="/dashboard"
                        className={({ isActive }) =>
                            `py-3 px-6 ${isActive ? "text-blue-600 font-medium bg-blue-50" : "text-gray-600 hover:bg-gray-50"}`
                        }
                    >
                        Dashboard
                    </NavLink>
                    <NavLink
                        to="/dashboard/bookings"
                        className={({ isActive }) =>
                            `py-3 px-6 ${isActive ? "text-blue-600 font-medium bg-blue-50" : "text-gray-600 hover:bg-gray-50"}`
                        }
                    >
                        Bookings
                    </NavLink>
                    <NavLink
                        to="/dashboard/jobcards"
                        className={({ isActive }) =>
                            `py-3 px-6 ${isActive ? "text-blue-600 font-medium bg-blue-50" : "text-gray-600 hover:bg-gray-50"}`
                        }
                    >
                        JobCards
                    </NavLink>
                    <NavLink
                        to="/reports"
                        className={({ isActive }) =>
                            `py-3 px-6 ${isActive ? "text-blue-600 font-medium bg-blue-50" : "text-gray-600 hover:bg-gray-50"}`
                        }
                    >
                        Reports
                    </NavLink>
                    <NavLink
                        to="/reminders"
                        className={({ isActive }) =>
                            `py-3 px-6 ${isActive ? "text-blue-600 font-medium bg-blue-50" : "text-gray-600 hover:bg-gray-50"}`
                        }
                    >
                        Reminders
                    </NavLink>
                </nav>
            </aside>

            {/* Main Content Area */}
            <div className="flex-1 flex flex-col">
                {/* Header */}
                <header className="h-16 bg-white border-b flex items-center justify-between px-6">
                    <h1 className="text-xl font-semibold text-gray-800">{title}</h1>
                    <button
                        onClick={handleLogout}
                        className="text-sm text-gray-700 hover:text-black transition-colors"
                    >
                        Logout
                    </button>
                </header>

                {/* Page Content */}
                <main className="flex-1 p-6 overflow-y-auto">
                    {children}
                </main>
            </div>
        </div>
    );
}
