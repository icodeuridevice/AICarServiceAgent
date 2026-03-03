export default function LoadingSpinner() {
    return (
        <div className="flex items-center justify-center py-10">
            <div className="animate-spin border-4 border-blue-600 border-t-transparent rounded-full h-8 w-8" />
        </div>
    );
}
