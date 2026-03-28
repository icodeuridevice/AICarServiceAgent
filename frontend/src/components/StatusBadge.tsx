interface StatusBadgeProps {
    status: string;
}

const styles: Record<string, string> = {
    PENDING: "bg-yellow-100 text-yellow-700",
    CONFIRMED: "bg-blue-100 text-blue-700",
    IN_PROGRESS: "bg-amber-100 text-amber-700",
    COMPLETED: "bg-green-100 text-green-700",
    CANCELLED: "bg-red-100 text-red-700",
};

export default function StatusBadge({ status }: StatusBadgeProps) {
    const badgeStyle = styles[status] ?? "bg-slate-100 text-slate-700";

    return (
        <span
            className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ${badgeStyle}`}
        >
            {status}
        </span>
    );
}
