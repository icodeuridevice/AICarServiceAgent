interface ErrorBannerProps {
    message: string;
}

export default function ErrorBanner({ message }: ErrorBannerProps) {
    return (
        <div className="bg-red-100 text-red-700 px-4 py-2 rounded-md border border-red-300" role="alert">
            {message}
        </div>
    );
}
