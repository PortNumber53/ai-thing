import {
  Outlet,
  Link,
  useRouteError,
  isRouteErrorResponse,
} from "@remix-run/react";

export function ErrorBoundary() {
  const error = useRouteError();
  const colors = {
    background: "bg-[#f6f5f4]",
    text: {
      primary: "text-[#2a2a2a]",
      secondary: "text-[#5c5c5c]",
    },
  };

  let title = "Unexpected Error";
  let message = "An unexpected error occurred. Please try again later.";

  if (isRouteErrorResponse(error)) {
    title = `${error.status} ${error.statusText}`;
    message = error.data;
  } else if (error instanceof Error) {
    message = error.message;
  }

  return (
    <div
      className={`min-h-screen ${colors.background} flex flex-col antialiased`}
    >
      {/* Header */}
      <header className="bg-white border-b border-gray-200 shadow-sm">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <Link to="/" className="flex items-center space-x-2">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-8 w-8 text-[#3584e4]"
                viewBox="0 0 24 24"
                fill="currentColor"
              >
                <title>Maurício Otta</title>
                <path d="M12 0c-6.626 0-12 5.373-12 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z" />
              </svg>
              <span className="text-[#2a2a2a]">Maurício Otta</span>
            </Link>
          </div>
          <nav>
            <ul className="flex space-x-6">
              <li>
                <Link
                  to="/blog"
                  className="text-gray-500 hover:text-[#3584e4] transition-colors"
                >
                  Blog
                </Link>
              </li>
              <li>
                <Link
                  to="/resume/current"
                  className="text-gray-500 hover:text-[#3584e4] transition-colors"
                >
                  Current Resume
                </Link>
              </li>
              <li>
                <Link
                  to="/portfolio"
                  className="text-gray-500 hover:text-[#3584e4] transition-colors"
                >
                  Portfolio
                </Link>
              </li>
            </ul>
          </nav>
        </div>
      </header>

      {/* Error Content */}
      <main className="container mx-auto px-4 py-12 flex-grow">
        <div className="max-w-4xl mx-auto">
          <div className="bg-white rounded-lg shadow-md p-8 text-center">
            <h1 className="text-4xl font-bold mb-4 text-gray-900">{title}</h1>
            <p className="text-lg text-gray-600 mb-8">{message}</p>
            <Link
              to="/"
              className="inline-flex items-center justify-center px-6 py-3 border border-transparent text-base font-medium rounded-md text-white bg-[#3584e4] hover:bg-[#1c71d8] transition-colors"
            >
              Return Home
            </Link>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="bg-white border-t border-gray-200 py-6">
        <div className="container mx-auto px-4 text-center">
          <p className={colors.text.secondary}>
            &copy; 2025 Mauricio S. Otta. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  );
}

export default function Layout() {
  // GNOME-inspired color palette
  const colors = {
    background: "bg-[#f6f5f4]",
    primary: "bg-[#3584e4]",
    text: {
      primary: "text-[#2a2a2a]",
      secondary: "text-[#5c5c5c]",
    },
    accent: "bg-[#4a90d9]",
  };

  return (
    <div
      className={`min-h-screen ${colors.background} flex flex-col antialiased`}
    >
      {/* Header */}
      <header className="bg-white border-b border-gray-200 shadow-sm">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <Link to="/" className="flex items-center space-x-2">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-8 w-8 text-[#3584e4]"
                viewBox="0 0 24 24"
                fill="currentColor"
              >
                <title>Maurício Otta</title>
                <path d="M12 0c-6.626 0-12 5.373-12 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z" />
              </svg>
              <span className="text-[#2a2a2a]">Maurício Otta</span>
            </Link>
          </div>
          <nav>
            <ul className="flex space-x-6">
              <li>
                <Link
                  to="/blog"
                  className="text-gray-500 hover:text-[#3584e4] transition-colors"
                >
                  Blog
                </Link>
              </li>
              <li>
                <Link
                  to="/resume/current"
                  className="text-gray-500 hover:text-[#3584e4] transition-colors"
                >
                  Current Resume
                </Link>
              </li>
              <li>
                <Link
                  to="/portfolio"
                  className="text-gray-500 hover:text-[#3584e4] transition-colors"
                >
                  Portfolio
                </Link>
              </li>
            </ul>
          </nav>
        </div>
      </header>

      {/* Outlet for nested routes */}
      <Outlet />

      {/* Footer */}
      <footer className="bg-white border-t border-gray-200 py-6">
        <div className="container mx-auto px-4 text-center">
          <p className={colors.text.secondary}>
            &copy; 2025 Mauricio S. Otta. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  );
}
