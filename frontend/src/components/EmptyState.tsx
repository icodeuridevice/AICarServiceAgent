interface EmptyStateProps {
    title: string;
    description: string;
}

export default function EmptyState({ title, description }: EmptyStateProps) {
    return (
        <div className="bg-white border rounded-md p-10 text-center text-gray-500">
            <p className="text-sm font-medium">{title}</p>
            <p className="mt-2 text-sm">{description}</p>
        </div>
    );
}
